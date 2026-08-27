from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest_asyncio
import redis.asyncio as aioredis
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.models import Base
from tests.db import TEST_DATABASE_URL


@pytest_asyncio.fixture(scope="function")
async def real_redis() -> AsyncGenerator[tuple[aioredis.Redis, str], None]:
    """
    Provides a real Redis client and a unique test key prefix.
    Cleans up all keys prefixed with test_prefix upon test teardown.
    """
    redis_url = (
        getattr(settings, "REDIS_URL", None)
        or getattr(settings, "REDIS_CACHE_URL", None)
        or "redis://localhost:6379/0"
    )
    client = aioredis.from_url(redis_url, decode_responses=False)
    prefix = f"test:{uuid4().hex[:8]}"

    try:
        await client.ping()
        yield client, prefix
    finally:
        try:
            keys = await client.keys(f"{prefix}:*")
            if keys:
                await client.delete(*keys)
        except Exception:
            pass
        await client.aclose()


@pytest_asyncio.fixture(scope="function")
async def real_db_session_factory() -> AsyncGenerator[
    async_sessionmaker[AsyncSession], None
]:
    """
    Provides an async sessionmaker bound to the real test PostgreSQL database.
    """
    async_url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def real_qdrant_test_collection() -> AsyncGenerator[
    tuple[AsyncQdrantClient, str], None
]:
    """
    Provides an AsyncQdrantClient connected to localhost:6333 and a uniquely named test collection.
    Automatically deletes the test collection on teardown.
    """
    from qdrant_client.http import models as qmodels

    qdrant = AsyncQdrantClient(host="localhost", port=6333, timeout=5.0)
    collection_name = f"test_col_{uuid4().hex[:8]}"

    try:
        await qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=1536,
                distance=qmodels.Distance.COSINE,
            ),
        )
        yield qdrant, collection_name
    finally:
        try:
            await qdrant.delete_collection(collection_name)
        except Exception:
            pass
        await qdrant.close()
