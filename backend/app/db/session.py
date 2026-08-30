from typing import Any

import redis.asyncio as async_redis
from fastapi import Request
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.db.base import Base  # noqa: F401

# Dependency Injection Provider Functions


async def get_db(request: Request):
    """
    FastAPI dependency injection provider to retrieve PostgreSQL database sessions.
    Fetches the session factory initialized in lifespan from request app state.
    """
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        raise RuntimeError(
            "Database session factory is not initialized in application state."
        )

    async with session_factory() as session:
        yield session


def get_redis(request: Request) -> async_redis.Redis:
    """
    FastAPI dependency injection provider to retrieve Redis client.
    Fetches the redis client initialized in lifespan from request app state.
    """
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise RuntimeError("Redis client is not initialized in application state.")
    return redis


def get_qdrant(request: Request) -> AsyncQdrantClient:
    """
    FastAPI dependency injection provider to retrieve Qdrant client.
    Fetches the qdrant client initialized in lifespan from request app state.
    """
    qdrant = getattr(request.app.state, "qdrant", None)
    if qdrant is None:
        raise RuntimeError("Qdrant client is not initialized in application state.")
    return qdrant


# Client Initialization Helper Functions


def init_postgres_engine(database_url: str) -> AsyncEngine:
    """
    Instantiates the Async SQLAlchemy PostgreSQL database engine with connection pooling and timeouts.
    """
    # Force use of asyncpg driver
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine_kwargs: dict[str, Any] = {
        "pool_size": 20,
        "max_overflow": 10,
        "pool_timeout": 30.0,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
        "echo": False,
    }

    # Handle PgBouncer/Supabase session mode
    if "pgbouncer=true" in database_url.lower():
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        parsed = urlparse(database_url)
        qsl = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() != "pgbouncer"]
        database_url = urlunparse(parsed._replace(query=urlencode(qsl)))

    # Set statement_cache_size=0 for pgbouncer/shared pool compatibility
    engine_kwargs["connect_args"] = {"statement_cache_size": 0}

    return create_async_engine(database_url, **engine_kwargs)


def init_redis_client(
    host: str | None = None,
    port: int | None = None,
    password: str | None = None,
    ssl: bool = False,
    url: str | None = None,
) -> async_redis.Redis:
    """
    Instantiates the Redis key-value cache client connection pool or from a connection URL.
    """
    if url:
        pool = async_redis.ConnectionPool.from_url(
            url,
            decode_responses=True,
            socket_timeout=3.0,
            socket_connect_timeout=3.0,
            max_connections=50,
        )
    else:
        connection_class = async_redis.SSLConnection if ssl else async_redis.Connection
        pool = async_redis.ConnectionPool(
            host=host or "localhost",
            port=port or 6379,
            password=password,
            connection_class=connection_class,
            decode_responses=True,
            socket_timeout=3.0,
            socket_connect_timeout=3.0,
            max_connections=50,
        )
    return async_redis.Redis(connection_pool=pool)


def init_qdrant_client(
    host: str | None = None,
    port: int | None = None,
    api_key: str | None = None,
    url: str | None = None,
) -> AsyncQdrantClient:
    """
    Instantiates the Qdrant approximate nearest neighbor client.
    """
    if url:
        return AsyncQdrantClient(url=url, api_key=api_key, timeout=3)
    if host and (host.startswith("http://") or host.startswith("https://")):
        return AsyncQdrantClient(url=host, api_key=api_key, timeout=3)
    return AsyncQdrantClient(host=host, port=port, api_key=api_key, timeout=3)
