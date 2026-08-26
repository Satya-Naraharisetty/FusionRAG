from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.queue.interfaces import (
    Job,
    JobDispatcher,
    JobHandler,
    JobResult,
    JobStatus,
)


def test_job_serialization_and_deserialization():
    job_id = uuid4()
    now = datetime.now(UTC)
    payload = {"document_id": str(uuid4()), "user_id": str(uuid4()), "force": True}

    job = Job(
        job_id=job_id,
        task_type="PROCESS_DOCUMENT",
        payload=payload,
        attempt=2,
        max_attempts=5,
        created_at=now,
        correlation_id="corr-1234",
    )

    data = job.model_dump_json_safe()
    assert data["job_id"] == str(job_id)
    assert data["task_type"] == "PROCESS_DOCUMENT"
    assert data["attempt"] == 2
    assert data["max_attempts"] == 5
    assert data["correlation_id"] == "corr-1234"
    assert data["payload"] == payload

    reconstructed = Job.from_dict(data)
    assert reconstructed.job_id == job_id
    assert reconstructed.task_type == "PROCESS_DOCUMENT"
    assert reconstructed.attempt == 2
    assert reconstructed.max_attempts == 5
    assert reconstructed.payload == payload
    assert reconstructed.correlation_id == "corr-1234"


@pytest.mark.asyncio
async def test_job_dispatcher_routes_correctly():
    dispatcher = JobDispatcher()

    class DummyHandler(JobHandler):
        def __init__(self):
            self.handled_jobs: list[Job] = []

        async def handle(self, job: Job) -> JobResult:
            self.handled_jobs.append(job)
            return JobResult(success=True, details={"count": 42})

    handler = DummyHandler()
    dispatcher.register("TEST_TASK", handler)

    job = Job(task_type="TEST_TASK", payload={"msg": "hello"})
    result = await dispatcher.dispatch(job)

    assert result.success is True
    assert result.details == {"count": 42}
    assert len(handler.handled_jobs) == 1
    assert handler.handled_jobs[0].job_id == job.job_id


@pytest.mark.asyncio
async def test_job_dispatcher_missing_handler():
    dispatcher = JobDispatcher()
    job = Job(task_type="UNREGISTERED_TASK", payload={})

    result = await dispatcher.dispatch(job)
    assert result.success is False
    assert result.retryable is False
    assert "No handler registered" in (result.error or "")


@pytest.mark.asyncio
async def test_job_dispatcher_exception_wrapping():
    dispatcher = JobDispatcher()

    class FailingHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            raise ConnectionError("Simulated remote connection failure")

    dispatcher.register("FAILING_TASK", FailingHandler())
    job = Job(task_type="FAILING_TASK", payload={})

    result = await dispatcher.dispatch(job)
    assert result.success is False
    assert result.retryable is True
    assert "Simulated remote connection failure" in (result.error or "")


def test_job_status_enum_values():
    assert JobStatus.ENQUEUED.value == "ENQUEUED"
    assert JobStatus.PROCESSING.value == "PROCESSING"
    assert JobStatus.RETRYING.value == "RETRYING"
    assert JobStatus.COMPLETED.value == "COMPLETED"
    assert JobStatus.FAILED.value == "FAILED"
    assert JobStatus.DEAD_LETTER.value == "DEAD_LETTER"
