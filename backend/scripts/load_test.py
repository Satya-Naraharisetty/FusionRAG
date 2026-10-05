#!/usr/bin/env python3
"""
Asynchronous Load & Soak Testing Harness for FusionRAG.

Simulates concurrent user traffic over HTTP and Server-Sent Events (SSE) streaming.
Measures:
- Latency percentiles (min, p50, p90, p95, p99, max)
- First-token latency (Time-to-First-Token / TTFT)
- Streaming throughput (tokens/sec, requests/sec)
- Error and timeout rates
"""

import argparse
import asyncio
import json
import logging
import time
import uuid
from typing import Any

import httpx

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("load_test")


class LoadTestMetrics:
    def __init__(self) -> None:
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.latencies: list[float] = []
        self.ttft_latencies: list[float] = []
        self.total_tokens_received = 0
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def record_success(
        self, duration: float, ttft: float | None = None, tokens: int = 0
    ) -> None:
        self.total_requests += 1
        self.successful_requests += 1
        self.latencies.append(duration)
        if ttft is not None:
            self.ttft_latencies.append(ttft)
        self.total_tokens_received += tokens

    def record_failure(self, duration: float) -> None:
        self.total_requests += 1
        self.failed_requests += 1
        self.latencies.append(duration)

    def summary(self) -> dict[str, Any]:
        total_time = max(0.001, self.end_time - self.start_time)
        sorted_lat = sorted(self.latencies) if self.latencies else [0.0]

        def percentile(data: list[float], p: float) -> float:
            if not data:
                return 0.0
            idx = int(len(data) * p)
            return data[min(idx, len(data) - 1)]

        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "error_rate_pct": round(
                (self.failed_requests / max(1, self.total_requests)) * 100, 2
            ),
            "throughput_rps": round(self.successful_requests / total_time, 2),
            "total_tokens_received": self.total_tokens_received,
            "tokens_per_second": round(self.total_tokens_received / total_time, 2),
            "latency_p50_s": round(percentile(sorted_lat, 0.50), 3),
            "latency_p90_s": round(percentile(sorted_lat, 0.90), 3),
            "latency_p95_s": round(percentile(sorted_lat, 0.95), 3),
            "latency_p99_s": round(percentile(sorted_lat, 0.99), 3),
            "latency_max_s": round(max(sorted_lat), 3),
        }


async def simulate_user_session(
    user_id: int,
    base_url: str,
    requests_per_user: int,
    stream: bool,
    metrics: LoadTestMetrics,
) -> None:
    client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
    try:
        # Register throwaway user
        email = f"loadtest_{uuid.uuid4().hex[:8]}@example.com"
        password = "LoadPassword123!"
        reg_res = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        )

        token = ""
        if reg_res.status_code == 200:
            token = reg_res.json().get("access_token", "")
        else:
            # Fallback to login if already exists
            login_res = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": password}
            )
            if login_res.status_code == 200:
                token = login_res.json().get("access_token", "")

        headers = {"Authorization": f"Bearer {token}"} if token else {}

        questions = [
            "What is Fusion RAG?",
            "How does hybrid retrieval combine dense and sparse search?",
            "What are the benefits of cross-encoder reranking?",
            "Explain reciprocal rank fusion scoring formula.",
        ]

        for req_idx in range(requests_per_user):
            q = questions[req_idx % len(questions)]
            t0 = time.perf_counter()
            try:
                if stream:
                    tokens = 0
                    ttft = None
                    async with client.stream(
                        "POST",
                        "/api/v1/chat",
                        json={"question": q, "stream": True},
                        headers=headers,
                    ) as response:
                        if response.status_code != 200:
                            metrics.record_failure(time.perf_counter() - t0)
                            continue
                        async for line in response.aiter_lines():
                            if line.startswith("data:") and "delta" in line:
                                if ttft is None:
                                    ttft = time.perf_counter() - t0
                                tokens += 1
                    metrics.record_success(
                        time.perf_counter() - t0, ttft=ttft, tokens=tokens
                    )
                else:
                    res = await client.post(
                        "/api/v1/chat",
                        json={"question": q, "stream": False},
                        headers=headers,
                    )
                    if res.status_code == 200:
                        metrics.record_success(time.perf_counter() - t0)
                    else:
                        metrics.record_failure(time.perf_counter() - t0)
            except Exception:
                metrics.record_failure(time.perf_counter() - t0)
    finally:
        await client.aclose()


async def run_load_test(
    base_url: str, concurrency: int, requests_per_user: int, stream: bool
) -> dict[str, Any]:
    logger.info(
        f"Starting Load Test: concurrency={concurrency}, requests_per_user={requests_per_user}, stream={stream}"
    )
    metrics = LoadTestMetrics()
    metrics.start_time = time.perf_counter()

    tasks = [
        simulate_user_session(
            user_id=i,
            base_url=base_url,
            requests_per_user=requests_per_user,
            stream=stream,
            metrics=metrics,
        )
        for i in range(concurrency)
    ]
    await asyncio.gather(*tasks)

    metrics.end_time = time.perf_counter()
    summary = metrics.summary()

    print("\n" + "=" * 60)
    print("           FUSION RAG LOAD TEST SUMMARY REPORT")
    print("=" * 60)
    for k, v in summary.items():
        print(f"  {k:.<35} {v}")
    print("=" * 60 + "\n")

    return summary


def main():
    parser = argparse.ArgumentParser(description="FusionRAG Load Testing CLI")
    parser.add_argument(
        "--url", default="http://localhost:8000", help="Base backend URL"
    )
    parser.add_argument(
        "--concurrency", type=int, default=10, help="Number of concurrent user sessions"
    )
    parser.add_argument("--requests", type=int, default=5, help="Requests per user")
    parser.add_argument(
        "--stream", action="store_true", help="Test streaming SSE endpoint"
    )
    parser.add_argument("--output-json", help="Path to write JSON benchmark summary")

    args = parser.parse_args()
    summary = asyncio.run(
        run_load_test(
            base_url=args.url,
            concurrency=args.concurrency,
            requests_per_user=args.requests,
            stream=args.stream,
        )
    )

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Summary written to {args.output_json}")


if __name__ == "__main__":
    main()
