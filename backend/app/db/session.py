import redis
from fastapi import Request
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Central declarative base class for all SQLAlchemy ORM models.
    """

    pass


# Dependency Injection Provider Functions


def get_db(request: Request):
    """
    FastAPI dependency injection provider to retrieve PostgreSQL database sessions.
    Fetches the session factory initialized in lifespan from request app state.
    """
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        raise RuntimeError(
            "Database session factory is not initialized in application state."
        )

    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_redis(request: Request) -> redis.Redis:
    """
    FastAPI dependency injection provider to retrieve the lifespan-managed Redis client.
    """
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized in application state.")
    return redis_client


def get_qdrant(request: Request) -> QdrantClient:
    """
    FastAPI DI provider to retrieve the lifespan-managed Qdrant client.
    """
    qdrant_client = getattr(request.app.state, "qdrant", None)
    if qdrant_client is None:
        raise RuntimeError("Qdrant client is not initialized in application state.")
    return qdrant_client


# Client Initialization Helper Functions


def init_postgres_engine(database_url: str) -> Engine:
    """
    Instantiates a database engine with connection pooling parameters.
    """
    return create_engine(
        database_url,
        pool_pre_ping=True,  # Validates connection health before handing it to a worker
        pool_size=10,
        max_overflow=20,
    )


_redis_pool = None


def init_redis_client(host: str, port: int) -> redis.Redis:
    """
    Instantiates the Redis key-value cache client connection pool.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool(
            host=host,
            port=port,
            decode_responses=True,
            socket_timeout=3.0,
            socket_connect_timeout=3.0,
            max_connections=50,  # Optimized production size
        )
    return redis.Redis(connection_pool=_redis_pool)


def init_qdrant_client(host: str, port: int) -> QdrantClient:
    """
    Instantiates the Qdrant approximate nearest neighbor client.
    """
    return QdrantClient(host=host, port=port, timeout=3.0)
