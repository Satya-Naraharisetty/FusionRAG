import json
from unittest.mock import AsyncMock

import pytest

from app.core.queue.interfaces import Job
from app.core.queue.redis_queue import RedisStreamTaskQueue


@pytest.mark.asyncio
async def test_route_to_dead_letter_writes_sanitized_dlq_stream():
    mock_redis = AsyncMock()
    queue = RedisStreamTaskQueue(
        redis_client=mock_redis,
        dead_letter_stream="stream:jobs:dead_letter",
    )

    job = Job(
        task_type="PROCESS_DOCUMENT",
        payload={"doc_id": "123"},
        attempt=3,
        max_attempts=3,
        correlation_id="corr-test",
    )

    secret_error = "Failed to connect using Bearer secret_api_key_12345"
    await queue.route_to_dead_letter(
        job, secret_error, error_type="MaxAttemptsExceeded"
    )

    mock_redis.xadd.assert_called_once()
    call_kwargs = mock_redis.xadd.call_args[1]
    assert call_kwargs["name"] == "stream:jobs:dead_letter"

    dlq_data = json.loads(call_kwargs["fields"]["data"])
    assert dlq_data["job_id"] == str(job.job_id)
    assert dlq_data["task_type"] == "PROCESS_DOCUMENT"
    assert dlq_data["attempt"] == 3
    assert dlq_data["max_attempts"] == 3
    assert dlq_data["error_type"] == "MaxAttemptsExceeded"
    assert "secret_api_key_12345" not in dlq_data["sanitized_error"]
    assert "[REDACTED]" in dlq_data["sanitized_error"]
    assert dlq_data["correlation_id"] == "corr-test"
    assert dlq_data["payload"] == {"doc_id": "123"}
