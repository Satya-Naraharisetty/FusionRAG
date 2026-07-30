import logging

import redis
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session
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


@router.get("/health/liveness", response_model=LivenessResponse)
def liveness_check():
    """
    Lightweight health check probe verifying the FastAPI event loop is responsive.
    """
    return LivenessResponse(status="alive")


@router.get("/health/readiness", response_model=ReadinessResponse)
def readiness_check(
    response: Response,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
    qdrant_client: QdrantClient = Depends(get_qdrant),
):
    """
    Deep readiness check probe verifying connections to backing database systems.
    Runs query/command pings with strict client socket timeouts.
    """
    postgres_status = "connected"
    redis_status = "connected"
    vector_db_status = "connected"
    is_ready = True

    # 1. PostgreSQL connection health verification
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Readiness PostgreSQL check failed: {e}")
        postgres_status = f"disconnected: {str(e)}"
        is_ready = False

    # 2. Redis cache connection health verification
    try:
        if not redis_client.ping():
            redis_status = "disconnected: PING returned false"
            is_ready = False
    except Exception as e:
        logger.error(f"Readiness Redis check failed: {e}")
        redis_status = f"disconnected: {str(e)}"
        is_ready = False

    # 3. Qdrant vector DB connection health verification
    try:
        qdrant_client.get_collections()
    except Exception as e:
        logger.error(f"Readiness Qdrant check failed: {e}")
        vector_db_status = f"disconnected: {str(e)}"
        is_ready = False

    # Map response status codes based on readiness outcome
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
