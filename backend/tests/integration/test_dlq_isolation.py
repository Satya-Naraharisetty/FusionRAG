import asyncio
import json
from uuid import uuid4

import pytest

from app.core.queue.interfaces import Job, JobDispatcher, JobHandler, JobResult
from app.core.queue.redis_queue import RedisStreamTaskQueue
from app.core.queue.worker import QueueWorker


@pytest.mark.asyncio
async def test_poison_jobs_isolated_to_dlq_while_valid_jobs_complete(real_redis):
    redis_client, prefix = real_redis
    stream_name = f"{prefix}:stream:dlq_iso"
    group_name = f"{prefix}:group:dlq_iso"
    retry_set = f"{prefix}:retry"
    dlq_stream = f"{prefix}:dlq"

    queue = RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        consumer_group=group_name,
        retry_sorted_set=retry_set,
        dead_letter_stream=dlq_stream,
        consumer_name="worker-dlq-tester",
    )
    await queue.ensure_consumer_group()

    completed_valid_jobs: list[str] = []

    class InterleavedHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            if job.payload.get("is_poison"):
                # Non-retryable poison error with secret in raw error
                return JobResult(
                    success=False,
                    error="Malformed document data with Bearer secret_token_xyz987",
                    retryable=False,
                )
            completed_valid_jobs.append(job.payload["name"])
            return JobResult(success=True)

    dispatcher = JobDispatcher()
    dispatcher.register("INTERLEAVED_TASK", InterleavedHandler())

    worker = QueueWorker(
        task_queue=queue,
        dispatcher=dispatcher,
        concurrency=2,
        block_ms=300,
    )

    # 1. Submit interleaved jobs:
    # VALID_1, POISON_1, VALID_2, VALID_3, POISON_2, VALID_4
    sequence = [
        ("v1", False),
        ("p1", True),
        ("v2", False),
        ("v3", False),
        ("p2", True),
        ("v4", False),
    ]

    for name, is_poison in sequence:
        await queue.enqueue(
            task_type="INTERLEAVED_TASK",
            payload={"name": name, "is_poison": is_poison, "id": str(uuid4())},
            max_attempts=3,
        )

    await worker.start()

    # 2. Wait for completion
    for _ in range(50):
        if len(completed_valid_jobs) >= 4:
            break
        await asyncio.sleep(0.05)

    await worker.stop()

    # 3. Verify all 4 valid jobs completed
    assert set(completed_valid_jobs) == {"v1", "v2", "v3", "v4"}

    # 4. Verify exactly 2 poison jobs entered DLQ
    dlq_entries = await redis_client.xrange(dlq_stream)
    assert len(dlq_entries) == 2

    # 5. Verify DLQ error payload is sanitized (no raw Bearer secrets)
    for _, payload_map in dlq_entries:
        data_json = json.loads(payload_map[b"data"].decode("utf-8"))
        sanitized_error = data_json.get("sanitized_error", "")
        assert "secret_token_xyz987" not in sanitized_error
        assert "[REDACTED]" in sanitized_error

    # 6. Verify PEL is 0 (all messages ACKed and removed from pending)
    pel_info = await redis_client.xpending(stream_name, group_name)
    assert pel_info["pending"] == 0
