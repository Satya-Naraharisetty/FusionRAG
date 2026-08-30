import argparse
import asyncio
import logging
import os
import statistics
import time
import uuid

import httpx

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("load_test")

API_URL = os.getenv("VITE_API_URL", "http://127.0.0.1:8000")

# Setup a clean corpus for repeatable BM25 indexing
TEST_DOC_CONTENT = """
The Fusion RAG Chatbot is designed to provide high-complexity production answers.
We combine dense vector retrieval and sparse BM25 retrieval to produce a hybrid retriever.
In our first milestone, we are focusing on improving performance and scalability.
The event loop thread must not be blocked by synchronous SQLAlchemy repository operations.
SQLAlchemy Session objects are not thread-safe, so we must never share them across threads.
Durable cleanup jobs must remain in PostgreSQL as the authoritative source of truth.
Redis async connection pools should be initialized during application startup and reused.
The in-memory index cache must have a configurable maximum capacity setting for memory safety.
Idempotency and retry with exponential backoff are key requirements for durable cleanup worker.
Regression tests must prove that batch status fetches replace the N+1 pattern in embeddings.
"""


async def register_and_login():
    email = f"loadtest_{uuid.uuid4().hex[:8]}@example.com"
    password = "SecurePassword123!"
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Register
        logger.info(f"Registering user: {email}")
        res = await client.post(
            f"{API_URL}/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        if res.status_code != 201:
            raise RuntimeError(f"Registration failed: {res.status_code} - {res.text}")

        # Login
        logger.info("Logging in...")
        res = await client.post(
            f"{API_URL}/api/v1/auth/login", json={"email": email, "password": password}
        )
        if res.status_code != 200:
            raise RuntimeError(f"Login failed: {res.status_code} - {res.text}")

        token = res.json()["access_token"]
        return token, email


async def upload_document(token):
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        logger.info("Uploading test document...")
        files = {
            "file": ("loadtest_doc.txt", TEST_DOC_CONTENT.encode("utf-8"), "text/plain")
        }
        res = await client.post(
            f"{API_URL}/api/v1/documents/upload", files=files, headers=headers
        )
        if res.status_code != 201:
            raise RuntimeError(f"Upload failed: {res.status_code} - {res.text}")
        doc_id = res.json()["id"]

        # Wait for status = COMPLETED
        logger.info("Waiting for ingestion processing...")
        for _ in range(15):
            res = await client.get(
                f"{API_URL}/api/v1/documents/{doc_id}/embeddings/status",
                headers=headers,
            )
            if res.status_code == 200:
                status = res.json().get("status")
                if status == "COMPLETED":
                    logger.info("Document ingested successfully.")
                    return doc_id
            await asyncio.sleep(1.0)
        raise RuntimeError("Document ingestion timed out.")


async def delete_document_and_user(token, doc_id, email):
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        if doc_id:
            logger.info("Deleting test document...")
            await client.delete(f"{API_URL}/api/v1/documents/{doc_id}", headers=headers)

        # Clean up database records (cascade delete user)
        # We can do this via direct SQLAlchemy query
        from sqlalchemy import create_engine, text

        db_url = os.getenv("DATABASE_URL")
        # Fallback if DB URL has pgbouncer
        if db_url and "pgbouncer=" in db_url.lower():
            from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

            parsed = urlparse(db_url)
            qsl = [
                (k, v) for k, v in parse_qsl(parsed.query) if k.lower() != "pgbouncer"
            ]
            db_url = urlunparse(parsed._replace(query=urlencode(qsl)))

        if db_url:
            logger.info(f"Purging test user {email} from database...")
            try:
                engine = create_engine(db_url)
                with engine.connect() as conn:
                    trans = conn.begin()
                    conn.execute(
                        text("DELETE FROM users WHERE email = :email"), {"email": email}
                    )
                    trans.commit()
                logger.info("Test user purged.")
            except Exception as e:
                logger.error(f"Failed to purge user: {e}")


async def run_client_task(token, duration, results_list, stop_event):
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=5.0) as client:
        while not stop_event.is_set():
            start_time = time.perf_counter()
            try:
                res = await client.post(
                    f"{API_URL}/api/v1/search",
                    json={
                        "query": "Fusion RAG performance and scalability",
                        "top_k": 3,
                    },
                    headers=headers,
                )
                latency = time.perf_counter() - start_time
                success = res.status_code == 200
                results_list.append((latency, success))
            except Exception:
                latency = time.perf_counter() - start_time
                results_list.append((latency, False))
            # yield control briefly
            await asyncio.sleep(0.01)


def get_process_metrics():
    # Return memory usage for the uvicorn processes using powershell on Windows
    import subprocess

    try:
        cmd = 'powershell -Command "Get-Process -Name python, uvicorn -ErrorAction SilentlyContinue | Select-Object -Property WorkingSet64"'
        out = subprocess.check_output(cmd, shell=True, text=True).strip().splitlines()
        tot_mem_mb = 0.0
        for line in out:
            val = line.strip()
            if val.isdigit():
                tot_mem_mb += float(val) / (1024 * 1024)
        return tot_mem_mb
    except Exception:
        pass
    return 0.0


async def run_benchmark(token, concurrency, duration, warmup):
    # Warm-up phase
    if warmup > 0:
        logger.info(f"Starting warm-up for {warmup} seconds...")
        stop_event = asyncio.Event()
        warmup_results = []
        tasks = [
            asyncio.create_task(
                run_client_task(token, warmup, warmup_results, stop_event)
            )
            for _ in range(concurrency)
        ]
        await asyncio.sleep(warmup)
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Warm-up completed.")

    logger.info(
        f"Running benchmark with concurrency={concurrency} for {duration} seconds..."
    )
    stop_event = asyncio.Event()
    results = []

    # Track metrics
    start_time = time.time()
    tasks = [
        asyncio.create_task(run_client_task(token, duration, results, stop_event))
        for _ in range(concurrency)
    ]

    # Collect memory samples
    mem_samples = []
    for _ in range(int(duration)):
        mem_samples.append(get_process_metrics())
        await asyncio.sleep(1.0)

    stop_event.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    actual_duration = time.time() - start_time

    # Calculate statistics
    latencies = [r[0] for r in results if r[1]]
    errors = [r for r in results if not r[1]]
    total_requests = len(results)

    if not results:
        return {
            "concurrency": concurrency,
            "requests": 0,
            "rps": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "error_rate": 1.0,
            "memory_mb": 0.0,
        }

    error_rate = len(errors) / total_requests if total_requests > 0 else 0
    rps = total_requests / actual_duration if actual_duration > 0 else 0

    p50 = statistics.median(latencies) * 1000 if latencies else 0.0
    p95 = (
        statistics.quantiles(latencies, n=20)[18] * 1000
        if len(latencies) >= 20
        else (max(latencies) * 1000 if latencies else 0.0)
    )
    p99 = (
        statistics.quantiles(latencies, n=100)[98] * 1000
        if len(latencies) >= 100
        else (max(latencies) * 1000 if latencies else 0.0)
    )
    avg_mem = sum(mem_samples) / len(mem_samples) if mem_samples else 0.0

    return {
        "concurrency": concurrency,
        "requests": total_requests,
        "rps": rps,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "error_rate": error_rate,
        "memory_mb": avg_mem,
    }


async def main():
    parser = argparse.ArgumentParser(description="Fusion RAG Chatbot Load Testing Tool")
    parser.add_argument(
        "--warmup", type=int, default=3, help="Warm-up period in seconds"
    )
    parser.add_argument(
        "--duration", type=int, default=5, help="Measurement duration in seconds"
    )
    parser.add_argument(
        "--runs", type=int, default=3, help="Number of runs per concurrency level"
    )
    parser.add_argument(
        "--concurrency",
        type=str,
        default="10,25,50",
        help="Comma-separated concurrency levels",
    )

    args = parser.parse_args()
    concurrency_levels = [int(c.strip()) for c in args.concurrency.split(",")]

    token = None
    doc_id = None
    email = None
    try:
        token, email = await register_and_login()
        doc_id = await upload_document(token)

        final_results = {}
        for c in concurrency_levels:
            logger.info(f"=== Concurrency Tier: {c} ===")
            runs_stats = []
            for run in range(1, args.runs + 1):
                logger.info(f"Run {run} of {args.runs}...")
                stats = await run_benchmark(token, c, args.duration, args.warmup)
                runs_stats.append(stats)
                await asyncio.sleep(1.0)

            # Average the runs
            avg_rps = sum(s["rps"] for s in runs_stats) / len(runs_stats)
            avg_p50 = sum(s["p50_ms"] for s in runs_stats) / len(runs_stats)
            avg_p95 = sum(s["p95_ms"] for s in runs_stats) / len(runs_stats)
            avg_p99 = sum(s["p99_ms"] for s in runs_stats) / len(runs_stats)
            avg_err = sum(s["error_rate"] for s in runs_stats) / len(runs_stats)
            avg_mem = sum(s["memory_mb"] for s in runs_stats) / len(runs_stats)

            final_results[c] = {
                "rps": avg_rps,
                "p50_ms": avg_p50,
                "p95_ms": avg_p95,
                "p99_ms": avg_p99,
                "error_rate": avg_err,
                "memory_mb": avg_mem,
            }

        # Print table
        print("\n" + "=" * 80)
        print("CONCURRENT LOAD TEST BENCHMARK RESULTS")
        print("=" * 80)
        print(
            f"{'Concurrency':<15} | {'RPS':<10} | {'p50 (ms)':<10} | {'p95 (ms)':<10} | {'p99 (ms)':<10} | {'Error Rate':<12} | {'Mem (MB)':<10}"
        )
        print("-" * 80)
        for c, s in final_results.items():
            print(
                f"{c:<15} | {s['rps']:<10.2f} | {s['p50_ms']:<10.1f} | {s['p95_ms']:<10.1f} | {s['p99_ms']:<10.1f} | {s['error_rate']:<12.2%} | {s['memory_mb']:<10.1f}"
            )
        print("=" * 80)

    except Exception as e:
        logger.error(f"Benchmark run failed: {e}")
    finally:
        if token:
            await delete_document_and_user(token, doc_id, email)


if __name__ == "__main__":
    asyncio.run(main())
