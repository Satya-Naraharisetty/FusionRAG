import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.auth.domain.schemas import UserDomain
from app.auth.infrastructure.persistence.repositories.user_repository import (
    SQLAlchemyUserRepository,
)
from app.db.models import Base
from tests.db import TEST_DATABASE_URL

ASYNC_TEST_DATABASE_URL = (
    TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    if not TEST_DATABASE_URL.startswith("postgresql+asyncpg://")
    else TEST_DATABASE_URL
)


@pytest.fixture(scope="function")
async def concurrency_async_db():
    sync_engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        Base.metadata.create_all(bind=sync_engine)
    finally:
        sync_engine.dispose()

    engine = create_async_engine(ASYNC_TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        await session.execute(text("DELETE FROM refresh_sessions;"))
        await session.execute(text("DELETE FROM users;"))
        await session.commit()

    yield session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_user_creation_isolation(concurrency_async_db):
    """
    Tests that multiple concurrent tasks creating separate users using distinct
    AsyncSession instances execute cleanly in parallel without task collisions.
    """
    session_factory = concurrency_async_db

    async def create_user_task(idx: int):
        async with session_factory() as session:
            repo = SQLAlchemyUserRepository(session)
            user = UserDomain(
                id=uuid.uuid4(),
                email=f"concurrent_user_{idx}_{uuid.uuid4().hex[:6]}@example.com",
                hashed_password="HashedPassword123!",
                role="user",
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            saved = await repo.save(user)
            await session.commit()
            return saved

    # Execute 10 parallel transactions
    results = await asyncio.gather(*(create_user_task(i) for i in range(10)))
    assert len(results) == 10
    saved_ids = {u.id for u in results}
    assert len(saved_ids) == 10


@pytest.mark.asyncio
async def test_concurrent_reads_no_blocking(concurrency_async_db):
    """
    Tests that high-concurrency read-only transactions on AsyncSession do not
    interfere with each other or initiate unnecessary commits.
    """
    session_factory = concurrency_async_db

    # Seed one user
    target_id = uuid.uuid4()
    target_email = "read_target@example.com"
    async with session_factory() as session:
        repo = SQLAlchemyUserRepository(session)
        user = UserDomain(
            id=target_id,
            email=target_email,
            hashed_password="HashedPassword123!",
            role="user",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await repo.save(user)
        await session.commit()

    async def read_user_task():
        async with session_factory() as session:
            repo = SQLAlchemyUserRepository(session)
            found = await repo.get_by_email(target_email)
            assert found is not None
            assert found.id == target_id
            return found

    # Execute 25 concurrent reads
    results = await asyncio.gather(*(read_user_task() for _ in range(25)))
    assert len(results) == 25
