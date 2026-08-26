from unittest.mock import AsyncMock

import pytest

from app.core.queue.interfaces import Job, JobDispatcher, JobHandler, JobResult
from app.core.queue.worker import QueueWorker


@pytest.mark.asyncio
async def test_worker_successful_handler_execution_and_ack():
    mock_queue = AsyncMock()
    dispatcher = JobDispatcher()

    class SuccessHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            return JobResult(success=True, details={"status": "ok"})

    dispatcher.register("SUCCESS_TASK", SuccessHandler())
    worker = QueueWorker(task_queue=mock_queue, dispatcher=dispatcher)

    job = Job(task_type="SUCCESS_TASK", payload={})
    result = await worker.handle_message("msg-101", job)

    assert result.success is True
    mock_queue.acknowledge.assert_called_once_with("msg-101")
    mock_queue.schedule_retry.assert_not_called()
    mock_queue.route_to_dead_letter.assert_not_called()


@pytest.mark.asyncio
async def test_worker_retryable_failure_schedules_retry():
    mock_queue = AsyncMock()
    dispatcher = JobDispatcher()

    class TransientFailingHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            return JobResult(
                success=False,
                error="Rate limited (HTTP 429)",
                retryable=True,
            )

    dispatcher.register("RETRY_TASK", TransientFailingHandler())
    worker = QueueWorker(
        task_queue=mock_queue,
        dispatcher=dispatcher,
        retry_base_delay=2.0,
        retry_max_delay=10.0,
    )

    job = Job(task_type="RETRY_TASK", payload={}, attempt=1, max_attempts=3)
    result = await worker.handle_message("msg-102", job)

    assert result.success is False
    assert result.retryable is True
    mock_queue.schedule_retry.assert_called_once()
    # It must ACK the stream message after transferring it to the retry sorted set
    mock_queue.acknowledge.assert_called_once_with("msg-102")
    mock_queue.route_to_dead_letter.assert_not_called()


@pytest.mark.asyncio
async def test_worker_permanent_failure_routes_to_dlq():
    mock_queue = AsyncMock()
    dispatcher = JobDispatcher()

    class PermanentFailingHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            return JobResult(
                success=False,
                error="Corrupted PDF bytes",
                retryable=False,
            )

    dispatcher.register("PERM_TASK", PermanentFailingHandler())
    worker = QueueWorker(task_queue=mock_queue, dispatcher=dispatcher)

    job = Job(task_type="PERM_TASK", payload={}, attempt=1, max_attempts=3)
    result = await worker.handle_message("msg-103", job)

    assert result.success is False
    assert result.retryable is False
    mock_queue.route_to_dead_letter.assert_called_once_with(
        job, "Corrupted PDF bytes", error_type="NonRetryableError"
    )
    mock_queue.acknowledge.assert_called_once_with("msg-103")
    mock_queue.schedule_retry.assert_not_called()


@pytest.mark.asyncio
async def test_worker_max_attempts_exhausted_routes_to_dlq():
    mock_queue = AsyncMock()
    dispatcher = JobDispatcher()

    class AlwaysFailsHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            return JobResult(
                success=False,
                error="Service unavailable (503)",
                retryable=True,
            )

    dispatcher.register("EXHAUST_TASK", AlwaysFailsHandler())
    worker = QueueWorker(task_queue=mock_queue, dispatcher=dispatcher)

    # Job is on its final allowed attempt (attempt 3 of 3)
    job = Job(task_type="EXHAUST_TASK", payload={}, attempt=3, max_attempts=3)
    result = await worker.handle_message("msg-104", job)

    assert result.success is False
    mock_queue.route_to_dead_letter.assert_called_once_with(
        job, "Service unavailable (503)", error_type="MaxAttemptsExceeded"
    )
    mock_queue.acknowledge.assert_called_once_with("msg-104")
    mock_queue.schedule_retry.assert_not_called()
