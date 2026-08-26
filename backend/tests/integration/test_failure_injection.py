import asyncio
import time
from uuid import uuid4

import pytest

from app.core.queue.interfaces import Job, JobDispatcher, JobHandler, JobResult
from app.core.queue.redis_queue import RedisStreamTaskQueue
from app.core.queue.worker import QueueWorker


@pytest.mark.asyncio
async def test_transient_failure_exponential_retry_and_dlq_exhaustion(real_redis):
    redis_client, prefix = real_redis
    stream_name = f"{prefix}:stream:fail_inj"
    group_name = f"{prefix}:group:fail_inj"
    retry_set = f"{prefix}:retry"
    dlq_stream = f"{prefix}:dlq"

    queue = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        retry_sorted_set=retry_set,
        dead_letter_stream=dlq_stream,
        consumer_name="worker-failure-injector",
    )
    await queue.ensure_consumer_group()

    call_history: list[dict] = []

    class FailingTransientHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            call_history.append({"attempt": job.attempt, "time": time.time()})
            if job.attempt == 1:
                return JobResult(success=False, error="HTTP 429 Rate Limited", retryable=True)
            elif job.attempt == 2:
                return JobResult(success=False, error="HTTP 503 Service Unavailable", retryable=True)
            else:
                return JobResult(success=False, error="Persistent 500 Failure", retryable=True)

    dispatcher = JobDispatcher()
    dispatcher.register("FLAKY_API_TASK", FailingTransientHandler())

    worker = QueueWorker(
        task_queue=queue,
        dispatcher=dispatcher,
        retry_base_delay=0.1,
        retry_max_delay=2.0,
    )

    # 1. Enqueue job with max_attempts=3
    await queue.enqueue(
        task_type="FLAKY_API_TASK",
        payload={"query": "transient_test", "id": str(uuid4())},
        max_attempts=3,
    )

    # Attempt 1: Worker handles message and returns retryable failure
    msg_id_1, read_job_1 = (await queue.read_messages(count=1, block_ms=500))[0]
    res1 = await worker.handle_message(msg_id_1, read_job_1)

    assert res1.success is False
    assert res1.retryable is True

    # Verify message is scheduled in Redis Sorted Set
    retry_count_1 = await redis_client.zcard(retry_set)
    assert retry_count_1 == 1

    # Verify original message is ACKed from stream PEL
    pel_1 = await redis_client.xpending(stream_name, group_name)
    assert pel_1["pending"] == 0

    # Wait for backoff delay (0.1s)
    await asyncio.sleep(0.15)

    # Pump scheduled retry back into the stream
    pumped_count = await queue.pump_scheduled_retries()
    assert pumped_count >= 1

    # Attempt 2: Read re-enqueued message from stream (attempt should be 2)
    msg_id_2, read_job_2 = (await queue.read_messages(count=1, block_ms=500))[0]
    assert read_job_2.attempt == 2
    res2 = await worker.handle_message(msg_id_2, read_job_2)

    assert res2.success is False
    assert res2.retryable is True

    # Wait for backoff delay (0.2s)
    await asyncio.sleep(0.25)

    # Pump retry back to stream again
    await queue.pump_scheduled_retries()

    # Attempt 3: Read re-enqueued message from stream (attempt should be 3)
    msg_id_3, read_job_3 = (await queue.read_messages(count=1, block_ms=500))[0]
    assert read_job_3.attempt == 3
    res3 = await worker.handle_message(msg_id_3, read_job_3)

    assert res3.success is False

    # Max attempts reached (3 >= 3) -> should be routed to DLQ stream!
    dlq_entries = await redis_client.xrange(dlq_stream)
    assert len(dlq_entries) == 1
    _, dlq_payload = dlq_entries[0]
    assert b"data" in dlq_payload or b"job" in dlq_payload or b"error_message" in dlq_payload

    # Retry set is now clean
    retry_final = await redis_client.zcard(retry_set)
    assert retry_final == 0
