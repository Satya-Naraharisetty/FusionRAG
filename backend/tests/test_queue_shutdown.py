import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.queue.interfaces import Job, JobDispatcher, JobHandler, JobResult
from app.core.queue.worker import QueueWorker


@pytest.mark.asyncio
async def test_worker_graceful_shutdown_stops_loops():
    mock_queue = AsyncMock()
    mock_queue.read_messages.return_value = []
    mock_queue.reclaim_orphaned_jobs.return_value = ("0-0", [])
    mock_queue.pump_scheduled_retries.return_value = 0

    dispatcher = JobDispatcher()
    worker = QueueWorker(
        task_queue=mock_queue,
        dispatcher=dispatcher,
        recovery_interval_s=100.0,
        retry_pump_interval_s=100.0,
    )

    await worker.start()
    assert worker.is_running is True

    await worker.stop(timeout_seconds=1.0)
    assert worker.is_running is False


@pytest.mark.asyncio
async def test_worker_shutdown_does_not_falsely_ack_unfinished_jobs():
    mock_queue = AsyncMock()
    dispatcher = JobDispatcher()

    job_started_event = asyncio.Event()

    class LongRunningHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            job_started_event.set()
            await asyncio.sleep(10.0)  # Long task
            return JobResult(success=True)

    dispatcher.register("LONG_TASK", LongRunningHandler())
    worker = QueueWorker(task_queue=mock_queue, dispatcher=dispatcher)

    job = Job(task_type="LONG_TASK", payload={})

    # Start handling task in background
    task = asyncio.create_task(worker.handle_message("msg-long-1", job))
    await job_started_event.wait()

    # Track in worker
    worker._in_flight_tasks.add(task)
    worker._is_running = True

    # Trigger stop with tiny timeout so task is cancelled before completing
    await worker.stop(timeout_seconds=0.05)

    # Must NOT have acknowledged the message
    mock_queue.acknowledge.assert_not_called()
