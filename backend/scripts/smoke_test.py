import argparse
import asyncio
import logging
import os
import sys
import uuid

import httpx
from sqlalchemy import create_engine, text

# Configure logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("smoke_test")


def get_env_or_default(key, default):
    # Check if loaded or fallback
    return os.getenv(key) or default


# Config variables
def create_smoke_engine(url: str):
    if url and "pgbouncer=" in url.lower():
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        parsed = urlparse(url)
        qsl = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() != "pgbouncer"]
        url = urlunparse(parsed._replace(query=urlencode(qsl)))

    return create_engine(url)


API_URL = get_env_or_default("VITE_API_URL", "http://localhost:8000")
POSTGRES_URL = get_env_or_default(
    "DATABASE_URL",
    "postgresql://postgres:postgres_secure_password_123@db:5432/hybrid_rag",
)
REDIS_HOST = get_env_or_default("REDIS_HOST", "redis")
REDIS_PORT = int(get_env_or_default("REDIS_PORT", "6379"))
QDRANT_HOST = get_env_or_default("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(get_env_or_default("QDRANT_PORT", "6333"))
STORAGE_PROVIDER = get_env_or_default("STORAGE_PROVIDER", "database")


async def run_quick_checks():
    logger.info("=== RUNNING QUICK SMOKE CHECKS ===")
    errors = []

    # 1. Test PostgreSQL connectivity
    logger.info("Verifying PostgreSQL connectivity...")
    try:
        engine = create_smoke_engine(POSTGRES_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL is ONLINE.")
    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        errors.append("PostgreSQL Offline")

    # 2. Test Redis connectivity
    logger.info("Verifying Redis connectivity...")
    try:
        import redis

        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_timeout=3.0)
        if r.ping():
            logger.info("Redis is ONLINE.")
        else:
            errors.append("Redis Ping Failed")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        errors.append("Redis Offline")

    # 3. Test Qdrant connectivity
    logger.info("Verifying Qdrant connectivity...")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"http://{QDRANT_HOST}:{QDRANT_PORT}/readyz")
            if res.status_code == 200:
                logger.info("Qdrant is ONLINE.")
            else:
                errors.append(f"Qdrant returned status {res.status_code}")
    except Exception as e:
        logger.error(f"Qdrant connection failed: {e}")
        errors.append("Qdrant Offline")

    # 4. Test API Health Readiness endpoint
    logger.info(f"Verifying API readiness endpoint on {API_URL}...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{API_URL}/api/v1/health/readiness")
            if res.status_code == 200:
                logger.info("API readiness health endpoint is GREEN.")
            else:
                errors.append(
                    f"API health returned status {res.status_code}: {res.text}"
                )
    except Exception as e:
        logger.error(f"API health connection failed: {e}")
        errors.append("API Offline")

    # 5. Check S3 if enabled
    if STORAGE_PROVIDER.lower() == "s3":
        logger.info("Verifying S3 storage connection (read-only checks)...")
        try:
            import boto3

            s3_bucket = get_env_or_default("S3_BUCKET", "hybrid-rag-documents")
            s3_endpoint = os.getenv("S3_ENDPOINT_URL")
            s3_access = os.getenv("S3_ACCESS_KEY_ID")
            s3_secret = os.getenv("S3_SECRET_ACCESS_KEY")
            s3_region = os.getenv("S3_REGION_NAME")

            client_kwargs = {}
            if s3_access:
                client_kwargs["aws_access_key_id"] = s3_access
            if s3_secret:
                client_kwargs["aws_secret_access_key"] = s3_secret
            if s3_region:
                client_kwargs["region_name"] = s3_region
            if s3_endpoint:
                client_kwargs["endpoint_url"] = s3_endpoint

            s3 = boto3.client("s3", **client_kwargs)
            s3.head_bucket(Bucket=s3_bucket)
            s3.list_objects_v2(Bucket=s3_bucket, MaxKeys=1)
            logger.info("S3 storage is ONLINE and accessible.")
        except Exception as e:
            logger.error(f"S3 storage check failed: {e}")
            errors.append(f"S3 Storage Offline: {e}")

    if errors:
        logger.error(f"Quick checks completed with ERRORS: {', '.join(errors)}")
        return False

    logger.info("All quick checks PASSED successfully.")
    return True


async def run_full_e2e_checks():
    logger.info("=== RUNNING FULL E2E SMOKE CHECKS ===")

    # Run quick checks first
    quick_passed = await run_quick_checks()
    if not quick_passed:
        return False

    temp_username = f"smoketest_{uuid.uuid4().hex[:6]}@example.com"
    temp_password = "SecurePassword_123!"
    headers = {}
    temp_user_id = None
    uploaded_doc_id = None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Register temporary user
            logger.info(f"Registering temporary user: {temp_username}...")
            register_payload = {"email": temp_username, "password": temp_password}
            res = await client.post(
                f"{API_URL}/api/v1/auth/register", json=register_payload
            )
            if res.status_code != 201:
                logger.error(f"Registration failed: {res.status_code} - {res.text}")
                return False

            user_data = res.json()
            temp_user_id = user_data["id"]
            logger.info(f"Temporary user registered successfully (ID: {temp_user_id}).")

            # 2. Login temporary user
            logger.info("Logging in temporary user...")
            login_payload = {"email": temp_username, "password": temp_password}
            res = await client.post(f"{API_URL}/api/v1/auth/login", json=login_payload)
            if res.status_code != 200:
                logger.error(f"Login failed: {res.status_code} - {res.text}")
                return False

            token_data = res.json()
            access_token = token_data["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}
            logger.info("Login successful. Headers configured.")

            # 3. Upload a sample document chunk
            logger.info("Uploading test document chunk...")
            test_content = b"This is a smoke test content for Hybrid RAG Chatbot validation. We are checking full flow."
            files = {"file": ("smoketest.txt", test_content, "text/plain")}
            res = await client.post(
                f"{API_URL}/api/v1/documents/upload", files=files, headers=headers
            )
            if res.status_code != 201:
                logger.error(f"Upload failed: {res.status_code} - {res.text}")
                return False

            doc_data = res.json()
            uploaded_doc_id = doc_data["id"]
            logger.info(f"Document uploaded successfully (ID: {uploaded_doc_id}).")

            # 4. Wait for processing completion (ingestion/embedding)
            logger.info("Waiting for document parsing and embedding completion...")
            max_attempts = 15
            for attempt in range(1, max_attempts + 1):
                res = await client.get(
                    f"{API_URL}/api/v1/documents/{uploaded_doc_id}/embeddings/status",
                    headers=headers,
                )
                if res.status_code == 200:
                    status_data = res.json()
                    status_str = status_data.get("status")
                    logger.info(
                        f"Checking status (attempt {attempt}/{max_attempts}): {status_str}"
                    )
                    if status_str == "COMPLETED":
                        logger.info(
                            "Document ingestion and embedding processing COMPLETED."
                        )
                        break
                    elif status_str == "FAILED":
                        logger.error(
                            f"Document processing FAILED: {status_data.get('failure_reason')}"
                        )
                        return False
                else:
                    logger.warning(f"Failed to fetch status: {res.status_code}")

                await asyncio.sleep(2.0)
            else:
                logger.error("Timeout waiting for document processing to complete.")
                return False

            # 5. Perform a hybrid search query
            logger.info("Executing hybrid search query...")
            search_url = f"{API_URL}/api/v1/search?query=hybrid+chatbot&limit=5"
            res = await client.get(search_url, headers=headers)
            if res.status_code != 200:
                logger.error(f"Hybrid search failed: {res.status_code} - {res.text}")
                return False

            search_results = res.json()
            logger.info(f"Hybrid search returned {len(search_results)} results.")

            # 6. Call Chat Streaming endpoint (SSE)
            logger.info("Testing Chat Streaming (SSE) response flow...")
            chat_payload = {
                "question": "What is the content of the uploaded smoketest document?",
                "stream": True,
            }

            async with client.stream(
                "POST", f"{API_URL}/api/v1/chat", json=chat_payload, headers=headers
            ) as response:
                if response.status_code != 200:
                    logger.error(f"Chat stream request failed: {response.status_code}")
                    return False

                event_count = 0
                async for line in response.aiter_lines():
                    if line.strip():
                        event_count += 1
                        if event_count <= 5:
                            logger.info(f"Stream Event Line: {line}")
                        if "event: error" in line:
                            logger.error(f"Error returned in SSE stream event: {line}")
                            return False

                logger.info(
                    f"Chat stream completed successfully. Received {event_count} stream data lines."
                )

    except Exception as e:
        logger.exception(f"Unhandled error occurred during E2E checks: {e}")
        return False

    finally:
        # Clean up resources to keep the tests idempotent
        logger.info("Initiating E2E teardown cleanup...")
        engine = create_smoke_engine(POSTGRES_URL)

        if uploaded_doc_id:
            logger.info(f"Deleting test document: {uploaded_doc_id}...")
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.delete(
                        f"{API_URL}/api/v1/documents/{uploaded_doc_id}", headers=headers
                    )
                logger.info("Document deleted.")
            except Exception as e:
                logger.error(f"Failed to delete test document: {e}")

        if temp_user_id:
            logger.info(f"Purging temporary user {temp_username} records from DB...")
            try:
                with engine.connect() as conn:
                    trans = conn.begin()
                    try:
                        # Cascade deletes should clean up related sessions/conversations
                        # Delete user
                        conn.execute(
                            text("DELETE FROM users WHERE id = :user_id"),
                            {"user_id": temp_user_id},
                        )
                        trans.commit()
                        logger.info("User records purged successfully.")
                    except Exception as e:
                        trans.rollback()
                        raise e
            except Exception as e:
                logger.error(f"Failed to purge temporary user database entries: {e}")

    logger.info("All E2E checks PASSED successfully.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hybrid RAG Chatbot Smoke Test Runner")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only quick connection checks for backing services",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run quick connection checks and full idempotent E2E validations",
    )

    args = parser.parse_args()

    # If no flag is provided, run quick checks by default
    if not args.quick and not args.full:
        args.quick = True

    if args.quick:
        success = asyncio.run(run_quick_checks())
    else:
        success = asyncio.run(run_full_e2e_checks())

    if success:
        logger.info("Smoke test completed with SUCCESS status.")
        sys.exit(0)
    else:
        logger.error("Smoke test failed.")
        sys.exit(1)
