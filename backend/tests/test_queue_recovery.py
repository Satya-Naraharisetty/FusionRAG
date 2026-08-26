import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.queue.interfaces import Job
from app.core.queue.redis_queue import RedisStreamTaskQueue


@pytest.mark.asyncio
async def test_reclaim_orphaned_jobs_via_xautoclaim():
    mock_redis = AsyncMock()
    sample_job = Job(
        job_id=uuid4(),
        task_type="PROCESS_DOCUMENT",
        payload={"doc_id": "999"},
        attempt=1,
        max_attempts=3,
    )
    json_data = json.dumps(sample_job.model_dump_json_safe())

    # xautoclaim return signature: (next_start_id, [(msg_id, {b'data': ...})], [deleted_ids])
    mock_redis.xautoclaim.return_value = (
        "0-0",
        [(b"1740000000000-0", {b"data": json_data.encode("utf-8")})],
        [],
    )

    queue = RedisStreamTaskQueue(
        redis_client=mock_redis,
        stream_name="stream:jobs:document_processing",
        consumer_group="group:document_workers",
        consumer_name="worker-replica-2",
    )

    next_id, claimed = await queue.reclaim_orphaned_jobs(
        min_idle_time_ms=60000, count=10, start_id="0-0"
    )

    assert next_id == "0-0"
    assert len(claimed) == 1
    msg_id, job = claimed[0]
    assert msg_id == "1740000000000-0"
    assert job.job_id == sample_job.job_id
    assert job.task_type == "PROCESS_DOCUMENT"

    mock_redis.xautoclaim.assert_called_once_with(
        name="stream:jobs:document_processing",
        groupname="group:document_workers",
        consumername="worker-replica-2",
        min_idle_time=60000,
        start_id="0-0",
        count=10,
    )
