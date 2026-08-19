from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.documents.infrastructure.persistence.models import SQLAlchemyCleanupJob
from app.documents.services.cleanup_worker import (
    DurableCleanupWorker,
    _query_pending_failed_jobs,
    async_durable_cleanup_recovery,
)


class MockResult:
    def __init__(self, jobs):
        self.jobs = jobs

    def scalar_one_or_none(self):
        return self.jobs[0] if self.jobs else None

    def scalars(self):
        return self

    def all(self):
        return self.jobs


class MockDB:
    def __init__(self, jobs):
        self.jobs = jobs
        self.flushed = False
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement):
        return MockResult(self.jobs)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def delete(self, instance):
        if instance in self.jobs:
            self.jobs.remove(instance)

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_cleanup_worker_process_job_success():
    job_id = uuid4()
    job = SQLAlchemyCleanupJob(
        id=job_id,
        status="PENDING",
        attempts=0,
        payload={
            "document_id": str(uuid4()),
            "user_id": str(uuid4()),
            "storage_key": "test_key",
            "qdrant_point_ids": [str(uuid4())],
        },
    )

    db = MockDB([job])
    storage = MagicMock()
    storage.delete = AsyncMock()
    vector = MagicMock()
    vector.delete = AsyncMock()
    vector.delete_document = AsyncMock()
    cache = MagicMock()

    worker = DurableCleanupWorker(db, storage, vector, cache)
    await worker.process_job(job_id)

    assert job.status == "COMPLETED"
    assert storage.delete.call_count == 1
    assert vector.delete.call_count == 1
    assert cache.invalidate.call_count == 1
    assert db.committed is True


@pytest.mark.asyncio
async def test_cleanup_worker_process_job_already_completed():
    job_id = uuid4()
    job = SQLAlchemyCleanupJob(
        id=job_id,
        status="COMPLETED",
        attempts=0,
        payload={},
    )

    db = MockDB([job])
    storage = MagicMock()
    storage.delete = AsyncMock()
    vector = MagicMock()
    cache = MagicMock()

    worker = DurableCleanupWorker(db, storage, vector, cache)
    await worker.process_job(job_id)

    assert job.status == "COMPLETED"
    assert storage.delete.call_count == 0


@pytest.mark.asyncio
async def test_async_durable_cleanup_recovery_triggers_jobs():
    job_ids = [uuid4(), uuid4()]

    # Mock the DB query to return our job IDs
    with patch(
        "app.documents.services.cleanup_worker._query_pending_failed_jobs",
        return_value=job_ids,
    ) as mock_query:
        with patch(
            "app.documents.services.cleanup_worker._run_cleanup_jobs_async"
        ) as mock_run:
            await async_durable_cleanup_recovery()

            mock_query.assert_called_once()
            mock_run.assert_called_once_with(job_ids)


@pytest.mark.asyncio
async def test_query_pending_failed_jobs_bounded():
    # Setup settings mock and DB mocks
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.DATABASE_URL = "postgresql://localhost:5432/mock"
        mock_settings.CLEANUP_RECOVERY_BATCH_SIZE = 5

        job1 = SQLAlchemyCleanupJob(id=uuid4(), status="PENDING")
        job2 = SQLAlchemyCleanupJob(id=uuid4(), status="FAILED")
        mock_db = MockDB([job1, job2])

        # Create a mock sessionmaker context manager that returns mock_db
        class MockSessionMaker:
            def __init__(self, bind=None):
                pass

            async def __aenter__(self):
                return mock_db

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        with patch("app.db.session.init_postgres_engine") as mock_engine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.dispose = AsyncMock()
            mock_engine.return_value = mock_engine_instance

            with patch(
                "sqlalchemy.ext.asyncio.async_sessionmaker",
                return_value=MockSessionMaker,
            ):
                job_ids = await _query_pending_failed_jobs()

                assert len(job_ids) == 2
                assert job1.id in job_ids
                assert job2.id in job_ids
