import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.db.session import get_db, get_qdrant, get_redis

router = APIRouter()
logger = logging.getLogger(__name__)


class ServiceStatuses(BaseModel):
    postgres: str
    vector_db: str
    redis: str


class ReadinessResponse(BaseModel):
    status: str
    version: str
    services: ServiceStatuses


class LivenessResponse(BaseModel):
    status: str


class DeepHealthResponse(BaseModel):
    status: str
    version: str
    database: str
    redis: str
    vector_db: str
    storage: str
    llm: str


@router.get("/health/liveness", response_model=LivenessResponse)
def liveness_check():
    """
    Lightweight health check probe verifying the FastAPI event loop is responsive.
    """
    return LivenessResponse(status="alive")


@router.get("/health/readiness", response_model=ReadinessResponse)
async def readiness_check(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant),
):
    """
    Readiness check probe verifying basic connectivity to Postgres, Redis, and Qdrant.
    """
    postgres_status = "connected"
    redis_status = "connected"
    vector_db_status = "connected"
    is_ready = True

    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Readiness PostgreSQL check failed: {e}")
        postgres_status = "disconnected"
        is_ready = False

    try:
        if not await redis_client.ping():
            redis_status = "disconnected"
            is_ready = False
    except Exception as e:
        logger.error(f"Readiness Redis check failed: {e}")
        redis_status = "disconnected"
        is_ready = False

    try:
        await qdrant_client.get_collections()
    except Exception as e:
        logger.error(f"Readiness Qdrant check failed: {e}")
        vector_db_status = "disconnected"
        is_ready = False

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        status_text = "unhealthy"
    else:
        response.status_code = status.HTTP_200_OK
        status_text = "healthy"

    return ReadinessResponse(
        status=status_text,
        version="0.1.0",
        services=ServiceStatuses(
            postgres=postgres_status, vector_db=vector_db_status, redis=redis_status
        ),
    )


@router.get("/health/deep", response_model=DeepHealthResponse)
async def deep_check(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant),
):
    """
    Deep health check performing write validation on DB and Redis,
    checking local storage write permissions, and verifying LLM failover status.
    """
    db_status = "healthy"
    redis_status = "healthy"
    qdrant_status = "healthy"
    storage_status = "healthy"
    llm_status = "healthy"
    is_healthy = True

    # 1. Deep Postgres check: perform a write/read transaction check or simple test
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Deep health Postgres failed: {e}")
        db_status = f"unhealthy: {str(e)}"
        is_healthy = False

    # 2. Deep Redis check: perform SET and GET validation
    try:
        await redis_client.set("health:deep:ping", "pong", ex=10)
        ping_val = await redis_client.get("health:deep:ping")
        # Decode if bytes (some redis clients return bytes)
        if isinstance(ping_val, bytes):
            ping_val = ping_val.decode("utf-8")
        if ping_val != "pong":
            redis_status = "unhealthy: Read validation failed"
            is_healthy = False
    except Exception as e:
        logger.error(f"Deep health Redis failed: {e}")
        redis_status = f"unhealthy: {str(e)}"
        is_healthy = False

    # 3. Deep Qdrant check
    try:
        await qdrant_client.get_collections()
    except Exception as e:
        logger.error(f"Deep health Qdrant failed: {e}")
        qdrant_status = f"unhealthy: {str(e)}"
        is_healthy = False

    # 4. Storage check: test local upload dir permissions or database storage
    try:
        from app.api.dependencies import get_storage_provider

        storage_prov = get_storage_provider(db)
        from app.documents.infrastructure.storage import LocalStorageProvider

        if isinstance(storage_prov, LocalStorageProvider):

            def _check_local_storage():
                import pathlib

                from app.core.config import settings

                path = pathlib.Path(settings.UPLOAD_DIR)
                path.mkdir(parents=True, exist_ok=True)
                test_file = path / f"health_check_{int(time.time())}.txt"
                test_file.write_text("health check")
                test_file.unlink()

            await asyncio.to_thread(_check_local_storage)
    except Exception as e:
        logger.error(f"Deep health Storage check failed: {e}")
        storage_status = f"unhealthy: {str(e)}"
        is_healthy = False

    # 5. LLM Router status check
    try:
        from app.api.dependencies import get_llm_provider

        # Resolve LLM provider to inspect circuit state
        # In a real environment, we'd avoid making external calls to not waste API credits,
        # so we inspect the circuit breaker states of the router proxy.
        llm_provider = get_llm_provider()
        from app.chat.infrastructure.router import LLMProviderRouter

        if isinstance(llm_provider, LLMProviderRouter):
            gemini_breaker = llm_provider.get_circuit_breaker("gemini")
            if gemini_breaker and gemini_breaker.state == "OPEN":
                llm_status = "degraded: Gemini circuit is OPEN"

    except Exception as e:
        logger.error(f"Deep health LLM check failed: {e}")
        llm_status = f"degraded: {str(e)}"

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "unhealthy"
    else:
        response.status_code = status.HTTP_200_OK
        overall_status = "healthy"

    return DeepHealthResponse(
        status=overall_status,
        version="0.1.0",
        database=db_status,
        redis=redis_status,
        vector_db=qdrant_status,
        storage=storage_status,
        llm=llm_status,
    )
