import asyncio
from uuid import uuid4

import pytest

from app.core.queue.interfaces import Job, JobDispatcher, JobHandler, JobResult
from app.core.queue.redis_queue import RedisStreamTaskQueue
from app.core.queue.worker import QueueWorker


@pytest.mark.asyncio
async def test_shutdown_job_finishes_within_grace_period(real_redis):
    """
    Case A: Job is running when shutdown is requested, but completes before
    timeout. Worker waits, job completes, and is cleanly ACKed.
    """
    redis_client, prefix = real_redis
    stream_name = f"{prefix}:stream:shut_a"
    group_name = f"{prefix}:group:shut_a"

    queue = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        consumer_name="worker-graceful-a",
    )
    await queue.ensure_consumer_group()

    completed: list[str] = []
    started = asyncio.Event()

    class GracePeriodHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            started.set()
            await asyncio.sleep(0.1)  # Takes 100ms
            completed.append(job.payload["name"])
            return JobResult(success=True)

    dispatcher = JobDispatcher()
    dispatcher.register("GRACE_TASK", GracePeriodHandler())

    worker = QueueWorker(
        task_queue=queue,
        dispatcher=dispatcher,
        concurrency=1,
        block_ms=300,
    )

    await queue.enqueue(task_type="GRACE_TASK", payload={"name": "grace_job_1"})
    await worker.start()

    # Wait until the worker picks up the job
    await asyncio.wait_for(started.wait(), timeout=3.0)
    assert worker.active_tasks_count >= 1 or len(completed) == 1

    # Request stop with grace period of 2.0s (sufficient for 0.1s job)
    await worker.stop(timeout_seconds=2.0)

    assert "grace_job_1" in completed

    # Message was ACKed
    pel = await redis_client.xpending(stream_name, group_name)
    assert pel["pending"] == 0


@pytest.mark.asyncio
async def test_shutdown_exceeding_grace_period_never_falsely_acks(real_redis):
    """
    Case B: Job exceeds grace period. Worker stops, cancels the in-flight task,
    and crucially NEVER falsely ACKs. The un-ACKed message remains in PEL and
    is subsequently reclaimed and processed by Worker B via XAUTOCLAIM.
    """
    redis_client, prefix = real_redis
    stream_name = f"{prefix}:stream:shut_b"
    group_name = f"{prefix}:group:shut_b"

    queue_a = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        consumer_name="worker-slow-a",
    )
    queue_b = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        consumer_name="worker-recovery-b",
    )
    await queue_a.ensure_consumer_group()

    started_by_a = asyncio.Event()

    class LongRunningHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            started_by_a.set()
            await asyncio.sleep(5.0)  # Exceeds grace period
            return JobResult(success=True)

    disp_a = JobDispatcher()
    disp_a.register("LONG_TASK", LongRunningHandler())

    worker_a = QueueWorker(
        task_queue=queue_a,
        dispatcher=disp_a,
        concurrency=1,
        block_ms=200,
    )

    await queue_a.enqueue(
        task_type="LONG_TASK", payload={"id": str(uuid4()), "doc": "uncompleted_work"}
    )
    await worker_a.start()

    # Wait until Worker A picks up the job
    await asyncio.wait_for(started_by_a.wait(), timeout=2.0)

    # Force stop Worker A with very short grace period (50ms)
    await worker_a.stop(timeout_seconds=0.05)

    # Invariant: The message MUST NOT be ACKed and MUST remain in PEL
    pel_after_shutdown = await redis_client.xpending(stream_name, group_name)
    assert pel_after_shutdown["pending"] == 1
    assert pel_after_shutdown["consumers"][0]["name"] == b"worker-slow-a"

    # Worker B reclaims the orphaned job after visibility timeout
    await asyncio.sleep(0.15)

    completed_by_b: list[str] = []

    class RecoveryHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            completed_by_b.append(job.payload["doc"])
            return JobResult(success=True)

    disp_b = JobDispatcher()
    disp_b.register("LONG_TASK", RecoveryHandler())

    _, claimed = await queue_b.reclaim_orphaned_jobs(min_idle_time_ms=100)
    assert len(claimed) == 1
    msg_id, job_b = claimed[0]

    worker_b = QueueWorker(task_queue=queue_b, dispatcher=disp_b)
    res_b = await worker_b.handle_message(msg_id, job_b, is_reclaimed=True)
    assert res_b.success is True
    assert "uncompleted_work" in completed_by_b

    # Verify message is now ACKed
    pel_final = await redis_client.xpending(stream_name, group_name)
    assert pel_final["pending"] == 0
