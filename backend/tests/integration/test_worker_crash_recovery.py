import asyncio
from uuid import uuid4

import pytest

from app.core.queue.interfaces import Job, JobDispatcher, JobHandler, JobResult
from app.core.queue.redis_queue import RedisStreamTaskQueue
from app.core.queue.worker import QueueWorker


@pytest.mark.asyncio
async def test_worker_crash_and_orphan_recovery_via_xautoclaim(real_redis):
    """
    Validates that when Worker A reads a message into PEL and crashes/terminates
    before XACK, Worker B reclaims the message via XAUTOCLAIM after visibility
    timeout and processes it to completion, clearing the PEL.
    """
    redis_client, prefix = real_redis
    stream_name = f"{prefix}:stream:crash_rec"
    group_name = f"{prefix}:group:crash_rec"

    queue_a = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        consumer_name="worker-alpha-victim",
    )
    queue_b = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        consumer_name="worker-beta-rescuer",
    )

    await queue_a.ensure_consumer_group()

    # 1. Enqueue job
    job = await queue_a.enqueue(
        task_type="PROCESS_CRASH_TEST",
        payload={"payload_key": "crash_data_123", "id": str(uuid4())},
        max_attempts=3,
    )

    # 2. Worker A reads message via XREADGROUP into PEL
    messages = await queue_a.read_messages(count=1, block_ms=500)
    assert len(messages) == 1
    msg_id, received_job = messages[0]
    assert received_job.job_id == job.job_id

    # Verify message is currently pending in PEL assigned to worker-alpha-victim
    pel_before = await redis_client.xpending(stream_name, group_name)
    assert pel_before["pending"] == 1
    assert pel_before["consumers"][0]["name"] == b"worker-alpha-victim"

    # Worker A "crashes" -> NO acknowledge(msg_id) is called.
    # 3. Wait for short visibility timeout (e.g. 100ms)
    await asyncio.sleep(0.15)

    # 4. Worker B reclaims orphaned job using XAUTOCLAIM with min_idle_time_ms=100
    next_id, claimed = await queue_b.reclaim_orphaned_jobs(
        min_idle_time_ms=100,
        count=10,
    )
    assert len(claimed) == 1
    claimed_msg_id, claimed_job = claimed[0]
    assert claimed_msg_id == msg_id
    assert claimed_job.job_id == job.job_id

    # 5. Worker B executes business logic and ACKs
    processed_rescued: list[Job] = []

    class RescuerHandler(JobHandler):
        async def handle(self, j: Job) -> JobResult:
            processed_rescued.append(j)
            return JobResult(success=True, details={"status": "rescued_and_completed"})

    disp_b = JobDispatcher()
    disp_b.register("PROCESS_CRASH_TEST", RescuerHandler())

    worker_b = QueueWorker(task_queue=queue_b, dispatcher=disp_b)
    result = await worker_b.handle_message(claimed_msg_id, claimed_job, is_reclaimed=True)

    assert result.success is True
    assert len(processed_rescued) == 1
    assert processed_rescued[0].job_id == job.job_id

    # 6. Verify PEL is now 0 (acknowledged)
    pel_after = await redis_client.xpending(stream_name, group_name)
    assert pel_after["pending"] == 0


@pytest.mark.asyncio
async def test_worker_crash_automated_recovery_loop(real_redis):
    """
    Validates that QueueWorker's background _recovery_loop automatically detects,
    claims, and processes orphaned messages in real time.
    """
    redis_client, prefix = real_redis
    stream_name = f"{prefix}:stream:auto_rec"
    group_name = f"{prefix}:group:auto_rec"

    queue_a = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        consumer_name="worker-crashed-1",
    )
    queue_b = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        consumer_name="worker-auto-rescuer-2",
    )

    await queue_a.ensure_consumer_group()

    # Enqueue 3 jobs
    for i in range(3):
        await queue_a.enqueue(
            task_type="ORPHAN_TASK",
            payload={"item": i},
            max_attempts=3,
        )

    # Worker A reads all 3 messages into PEL and disappears
    messages = await queue_a.read_messages(count=3, block_ms=500)
    assert len(messages) == 3

    pel_initial = await redis_client.xpending(stream_name, group_name)
    assert pel_initial["pending"] == 3

    # Wait for idle time
    await asyncio.sleep(0.15)

    rescued_items: list[int] = []

    class AutoRescuerHandler(JobHandler):
        async def handle(self, j: Job) -> JobResult:
            rescued_items.append(j.payload["item"])
            return JobResult(success=True)

    disp_b = JobDispatcher()
    disp_b.register("ORPHAN_TASK", AutoRescuerHandler())

    # Start Worker B with short recovery interval and short visibility timeout
    worker_b = QueueWorker(
        task_queue=queue_b,
        dispatcher=disp_b,
        visibility_timeout_s=0.1,
        recovery_interval_s=0.1,
    )

    await worker_b.start()

    # Wait for automatic recovery
    for _ in range(40):
        if len(rescued_items) >= 3:
            break
        await asyncio.sleep(0.05)

    await worker_b.stop()

    assert set(rescued_items) == {0, 1, 2}
    pel_final = await redis_client.xpending(stream_name, group_name)
    assert pel_final["pending"] == 0
