from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.documents.infrastructure.persistence.models import SQLAlchemyCleanupJob
from app.documents.services.cleanup_worker import (
    DurableCleanupWorker,
    _query_pending_failed_jobs,
    async_durable_cleanup_recovery,
)


class MockDB:
    def __init__(self, jobs):
        self.jobs = jobs
        self.flushed = False
        self.committed = False
        self.rolled_back = False

    def query(self, model):
        self.query_model = model
        return self

    def filter(self, condition):
        # simple mock filter
        return self

    def limit(self, limit_val):
        self.limit_val = limit_val
        return self

    def all(self):
        return self.jobs

    def first(self):
        return self.jobs[0] if self.jobs else None

    def flush(self):
        self.flushed = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
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
    vector = MagicMock()
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
    vector = MagicMock()
    cache = MagicMock()

    worker = DurableCleanupWorker(db, storage, vector, cache)
    await worker.process_job(job_id)

    assert job.status == "COMPLETED"
    assert storage.delete.call_count == 0


@pytest.mark.asyncio
async def test_async_durable_cleanup_recovery_triggers_jobs():
    job_ids = [uuid4(), uuid4()]

    # Mock the thread-based DB query to return our job IDs
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


def test_query_pending_failed_jobs_bounded():
    # Setup settings mock and DB mocks
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.DATABASE_URL = "postgresql://localhost:5432/mock"
        mock_settings.CLEANUP_RECOVERY_BATCH_SIZE = 5

        job1 = SQLAlchemyCleanupJob(id=uuid4(), status="PENDING")
        job2 = SQLAlchemyCleanupJob(id=uuid4(), status="FAILED")
        mock_db = MockDB([job1, job2])

        with patch("app.db.session.init_postgres_engine"):
            with patch("sqlalchemy.orm.sessionmaker", return_value=lambda: mock_db):
                job_ids = _query_pending_failed_jobs()

                assert len(job_ids) == 2
                assert job1.id in job_ids
                assert job2.id in job_ids
                assert mock_db.limit_val == 5
