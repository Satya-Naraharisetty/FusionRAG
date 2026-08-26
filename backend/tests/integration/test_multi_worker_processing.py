import asyncio
from uuid import uuid4

import pytest

from app.core.queue.interfaces import Job, JobDispatcher, JobHandler, JobResult
from app.core.queue.redis_queue import RedisStreamTaskQueue
from app.core.queue.worker import QueueWorker


@pytest.mark.asyncio
async def test_two_workers_concurrently_process_batch_of_10_jobs(real_redis):
    redis_client, prefix = real_redis
    stream_name = f"{prefix}:stream:jobs"
    group_name = f"{prefix}:group:workers"
    retry_set = f"{prefix}:retry"
    dlq_stream = f"{prefix}:dlq"

    queue_a = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        retry_sorted_set=retry_set,
        dead_letter_stream=dlq_stream,
        consumer_name="worker-consumer-alpha",
    )
    queue_b = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        retry_sorted_set=retry_set,
        dead_letter_stream=dlq_stream,
        consumer_name="worker-consumer-beta",
    )

    processed_by_a: list[str] = []
    processed_by_b: list[str] = []

    class WorkerAHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            await asyncio.sleep(0.01)
            processed_by_a.append(job.payload["index"])
            return JobResult(success=True)

    class WorkerBHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            await asyncio.sleep(0.01)
            processed_by_b.append(job.payload["index"])
            return JobResult(success=True)

    dispatcher_a = JobDispatcher()
    dispatcher_a.register("TEST_TASK", WorkerAHandler())

    dispatcher_b = JobDispatcher()
    dispatcher_b.register("TEST_TASK", WorkerBHandler())

    worker_a = QueueWorker(
        task_queue=queue_a,
        dispatcher=dispatcher_a,
        concurrency=4,
        block_ms=500,
    )
    worker_b = QueueWorker(
        task_queue=queue_b,
        dispatcher=dispatcher_b,
        concurrency=4,
        block_ms=500,
    )

    # 1. Enqueue 10 jobs before or during worker startup
    for i in range(10):
        await queue_a.enqueue(
            task_type="TEST_TASK",
            payload={"index": f"job_{i}", "uuid": str(uuid4())},
            max_attempts=3,
        )

    await worker_a.start()
    await worker_b.start()

    # 2. Wait until all 10 jobs are processed
    total_processed = 0
    for _ in range(50):
        total_processed = len(processed_by_a) + len(processed_by_b)
        if total_processed >= 10:
            break
        await asyncio.sleep(0.1)

    await worker_a.stop()
    await worker_b.stop()

    assert total_processed == 10
    all_processed = set(processed_by_a + processed_by_b)
    expected_indices = {f"job_{i}" for i in range(10)}
    assert all_processed == expected_indices

    # 3. Verify PEL is 0 (all messages ACKed)
    pel_info = await redis_client.xpending(stream_name, group_name)
    assert pel_info["pending"] == 0


@pytest.mark.asyncio
async def test_two_workers_concurrently_process_batch_of_50_jobs(real_redis):
    redis_client, prefix = real_redis
    stream_name = f"{prefix}:stream:jobs:50"
    group_name = f"{prefix}:group:workers:50"

    queue_a = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        consumer_name="worker-50-a",
    )
    queue_b = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        consumer_name="worker-50-b",
    )

    processed_by_a: list[int] = []
    processed_by_b: list[int] = []

    class FastHandlerA(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            processed_by_a.append(job.payload["num"])
            return JobResult(success=True)

    class FastHandlerB(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            processed_by_b.append(job.payload["num"])
            return JobResult(success=True)

    disp_a = JobDispatcher()
    disp_a.register("BATCH_JOB", FastHandlerA())

    disp_b = JobDispatcher()
    disp_b.register("BATCH_JOB", FastHandlerB())

    worker_a = QueueWorker(task_queue=queue_a, dispatcher=disp_a, concurrency=4, block_ms=300)
    worker_b = QueueWorker(task_queue=queue_b, dispatcher=disp_b, concurrency=4, block_ms=300)

    for i in range(50):
        await queue_a.enqueue(
            task_type="BATCH_JOB",
            payload={"num": i},
            max_attempts=3,
        )

    await worker_a.start()
    await worker_b.start()

    for _ in range(80):
        if len(processed_by_a) + len(processed_by_b) >= 50:
            break
        await asyncio.sleep(0.05)

    await worker_a.stop()
    await worker_b.stop()

    assert len(processed_by_a) + len(processed_by_b) == 50
    assert set(processed_by_a + processed_by_b) == set(range(50))

    pel_info = await redis_client.xpending(stream_name, group_name)
    assert pel_info["pending"] == 0
