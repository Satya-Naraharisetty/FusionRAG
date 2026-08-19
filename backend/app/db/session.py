import redis.asyncio as async_redis
from fastapi import Request
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """
    Central declarative base class for all SQLAlchemy ORM models.
    """

    pass


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
    FastAPI dependency injection provider to retrieve the lifespan-managed Redis client.
    """
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized in application state.")
    return redis_client


def get_qdrant(request: Request) -> AsyncQdrantClient:
    """
    FastAPI DI provider to retrieve the lifespan-managed Qdrant client.
    """
    qdrant_client = getattr(request.app.state, "qdrant", None)
    if qdrant_client is None:
        raise RuntimeError("Qdrant client is not initialized in application state.")
    return qdrant_client


# Client Initialization Helper Functions


def init_postgres_engine(database_url: str) -> AsyncEngine:
    """
    Instantiates an async database engine with connection pooling parameters.
    """
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_size": settings.DATABASE_POOL_SIZE,
        "max_overflow": settings.DATABASE_MAX_OVERFLOW,
    }

    # Normalize url scheme to postgresql+asyncpg
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    # Strip pgbouncer query parameter as psycopg2/asyncpg doesn't support it
    if database_url and "pgbouncer=" in database_url.lower():
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        parsed = urlparse(database_url)
        qsl = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() != "pgbouncer"]
        database_url = urlunparse(parsed._replace(query=urlencode(qsl)))

    return create_async_engine(database_url, **engine_kwargs)


_redis_pool = None


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
    global _redis_pool
    if _redis_pool is None:
        if url:
            _redis_pool = async_redis.ConnectionPool.from_url(
                url,
                decode_responses=True,
                socket_timeout=3.0,
                socket_connect_timeout=3.0,
                max_connections=50,
            )
        else:
            connection_class = (
                async_redis.SSLConnection if ssl else async_redis.Connection
            )
            _redis_pool = async_redis.ConnectionPool(
                host=host or "localhost",
                port=port or 6379,
                password=password,
                connection_class=connection_class,
                decode_responses=True,
                socket_timeout=3.0,
                socket_connect_timeout=3.0,
                max_connections=50,  # Optimized production size
            )
    return async_redis.Redis(connection_pool=_redis_pool)


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
