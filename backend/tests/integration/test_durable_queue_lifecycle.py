import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.queue.in_memory import InMemoryDurableTaskQueue
from app.core.queue.interfaces import Job, JobDispatcher, JobHandler, JobResult
from app.core.queue.redis_queue import RedisStreamTaskQueue
from app.core.queue.worker import QueueWorker


@pytest.mark.asyncio
async def test_in_memory_durable_queue_end_to_end():
    dispatcher = JobDispatcher()
    processed_jobs: list[Job] = []

    class ProcessingHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            processed_jobs.append(job)
            return JobResult(success=True, details={"processed": True})

    dispatcher.register("PROCESS_DOCUMENT", ProcessingHandler())
    queue = InMemoryDurableTaskQueue(dispatcher=dispatcher, auto_dispatch=True)

    job = await queue.enqueue(
        task_type="PROCESS_DOCUMENT",
        payload={"doc_id": "test-doc-123"},
        max_attempts=3,
        correlation_id="corr-1",
    )

    assert len(processed_jobs) == 1
    assert processed_jobs[0].job_id == job.job_id
    assert job.job_id in queue._acknowledged


@pytest.mark.asyncio
async def test_redis_durable_queue_lifecycle_simulation():
    mock_redis = AsyncMock()
    stream_store: list[tuple[str, dict[str, str]]] = []
    ack_store: set[str] = set()

    async def mock_xadd(name, fields, maxlen=None, approximate=True):
        msg_id = f"174000000000{len(stream_store)}-0"
        stream_store.append((msg_id, fields))
        return msg_id

    async def mock_xreadgroup(groupname, consumername, streams, count=10, block=2000):
        if not stream_store:
            return []
        entries = []
        for msg_id, fields in stream_store:
            if msg_id not in ack_store:
                entries.append(
                    (msg_id.encode("utf-8"), {b"data": fields["data"].encode("utf-8")})
                )
        return [(b"stream:jobs:document_processing", entries)]

    async def mock_xack(name, group, *msg_ids):
        for mid in msg_ids:
            ack_store.add(mid)
        return len(msg_ids)

    mock_redis.xadd.side_effect = mock_xadd
    mock_redis.xreadgroup.side_effect = mock_xreadgroup
    mock_redis.xack.side_effect = mock_xack

    queue = RedisStreamTaskQueue(
        redis_client=mock_redis,
        stream_name="stream:jobs:document_processing",
        consumer_group="group:document_workers",
    )

    dispatcher = JobDispatcher()
    handled_records: list[dict] = []

    class MockDocHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            handled_records.append(job.payload)
            return JobResult(success=True)

    dispatcher.register("PROCESS_DOCUMENT", MockDocHandler())

    # 1. Enqueue job
    job = await queue.enqueue(
        task_type="PROCESS_DOCUMENT",
        payload={"document_id": str(uuid4()), "user_id": str(uuid4())},
        max_attempts=3,
    )
    assert len(stream_store) == 1

    # 2. Worker processes message
    worker = QueueWorker(task_queue=queue, dispatcher=dispatcher)
    msg_id, read_job = (await queue.read_messages(count=1))[0]
    result = await worker.handle_message(msg_id, read_job)

    assert result.success is True
    assert len(handled_records) == 1
    assert handled_records[0] == job.payload
    assert msg_id in ack_store


@pytest.mark.asyncio
async def test_worker_crash_and_second_worker_reclaim_lifecycle():
    mock_redis = AsyncMock()

    crashed_job = Job(
        task_type="PROCESS_DOCUMENT",
        payload={"doc_id": "crashed_doc_456"},
        attempt=1,
        max_attempts=3,
    )
    crashed_msg_id = "1740000099999-0"
    json_bytes = json.dumps(crashed_job.model_dump_json_safe()).encode("utf-8")

    # Simulate XAUTOCLAIM returning the abandoned message to Worker B
    mock_redis.xautoclaim.return_value = (
        "0-0",
        [(crashed_msg_id.encode("utf-8"), {b"data": json_bytes})],
        [],
    )
    mock_redis.xack.return_value = 1

    queue_worker_b = RedisStreamTaskQueue(
        redis_client=mock_redis,
        consumer_name="worker-replica-b",
    )

    dispatcher = JobDispatcher()
    recovered_jobs: list[Job] = []

    class ReclaimHandler(JobHandler):
        async def handle(self, job: Job) -> JobResult:
            recovered_jobs.append(job)
            return JobResult(success=True)

    dispatcher.register("PROCESS_DOCUMENT", ReclaimHandler())
    worker_b = QueueWorker(task_queue=queue_worker_b, dispatcher=dispatcher)

    # Reclaim from PEL
    _, reclaimed = await queue_worker_b.reclaim_orphaned_jobs(min_idle_time_ms=60000)
    assert len(reclaimed) == 1

    msg_id, job_to_recover = reclaimed[0]
    result = await worker_b.handle_message(msg_id, job_to_recover, is_reclaimed=True)

    assert result.success is True
    assert len(recovered_jobs) == 1
    assert recovered_jobs[0].job_id == crashed_job.job_id
    mock_redis.xack.assert_called_once_with(
        "stream:jobs:document_processing",
        "group:document_workers",
        crashed_msg_id,
    )
