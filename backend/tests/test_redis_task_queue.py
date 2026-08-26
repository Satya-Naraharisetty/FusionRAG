import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from redis.exceptions import ResponseError

from app.core.queue.interfaces import Job
from app.core.queue.redis_queue import (
    RedisStreamTaskQueue,
    generate_consumer_name,
    sanitize_error_message,
)


def test_generate_consumer_name_is_unique_and_non_empty():
    name1 = generate_consumer_name()
    name2 = generate_consumer_name()
    assert name1 != name2
    assert len(name1) > 5


def test_sanitize_error_message():
    raw_error = "Connection failed with Bearer secret_jwt_token_12345 and password='super_secret_pwd'"
    sanitized = sanitize_error_message(raw_error)
    assert "secret_jwt_token_12345" not in sanitized
    assert "super_secret_pwd" not in sanitized
    assert "[REDACTED]" in sanitized


@pytest.mark.asyncio
async def test_ensure_consumer_group_creates_group():
    mock_redis = AsyncMock()
    queue = RedisStreamTaskQueue(
        redis_client=mock_redis,
        stream_name="test_stream",
        consumer_group="test_group",
    )

    await queue.ensure_consumer_group()
    mock_redis.xgroup_create.assert_called_once_with(
        name="test_stream", groupname="test_group", id="0", mkstream=True
    )


@pytest.mark.asyncio
async def test_ensure_consumer_group_handles_busygroup_gracefully():
    mock_redis = AsyncMock()
    mock_redis.xgroup_create.side_effect = ResponseError(
        "BUSYGROUP Consumer Group name already exists"
    )

    queue = RedisStreamTaskQueue(
        redis_client=mock_redis,
        stream_name="test_stream",
        consumer_group="test_group",
    )

    # Should not raise exception
    await queue.ensure_consumer_group()


@pytest.mark.asyncio
async def test_enqueue_calls_xadd_with_serialized_job():
    mock_redis = AsyncMock()
    mock_redis.xadd.return_value = "1740000000000-0"

    queue = RedisStreamTaskQueue(
        redis_client=mock_redis,
        stream_name="test_stream",
        max_stream_length=5000,
    )

    payload = {"doc_id": str(uuid4()), "user_id": str(uuid4())}
    job = await queue.enqueue(
        task_type="PROCESS_DOCUMENT",
        payload=payload,
        max_attempts=3,
        correlation_id="corr-abc",
    )

    assert job.task_type == "PROCESS_DOCUMENT"
    assert job.payload == payload
    assert job.max_attempts == 3
    assert job.correlation_id == "corr-abc"

    mock_redis.xadd.assert_called_once()
    call_kwargs = mock_redis.xadd.call_args[1]
    assert call_kwargs["name"] == "test_stream"
    assert call_kwargs["maxlen"] == 5000
    assert call_kwargs["approximate"] is True

    # Validate serialized data field
    raw_data = call_kwargs["fields"]["data"]
    parsed = json.loads(raw_data)
    assert parsed["job_id"] == str(job.job_id)
    assert parsed["task_type"] == "PROCESS_DOCUMENT"
    assert parsed["payload"] == payload


@pytest.mark.asyncio
async def test_acknowledge_calls_xack():
    mock_redis = AsyncMock()
    queue = RedisStreamTaskQueue(
        redis_client=mock_redis,
        stream_name="test_stream",
        consumer_group="test_group",
    )

    await queue.acknowledge("1740000000000-0")
    mock_redis.xack.assert_called_once_with(
        "test_stream", "test_group", "1740000000000-0"
    )


@pytest.mark.asyncio
async def test_read_messages_deserializes_correctly():
    mock_redis = AsyncMock()
    sample_job = Job(task_type="PROCESS_DOCUMENT", payload={"foo": "bar"})
    json_data = json.dumps(sample_job.model_dump_json_safe())

    mock_redis.xreadgroup.return_value = [
        (
            b"test_stream",
            [(b"1740000000000-0", {b"data": json_data.encode("utf-8")})],
        )
    ]

    queue = RedisStreamTaskQueue(
        redis_client=mock_redis,
        stream_name="test_stream",
        consumer_group="test_group",
    )

    messages = await queue.read_messages(count=5, block_ms=1000)
    assert len(messages) == 1
    msg_id, job = messages[0]
    assert msg_id == "1740000000000-0"
    assert job.job_id == sample_job.job_id
    assert job.task_type == "PROCESS_DOCUMENT"
    assert job.payload == {"foo": "bar"}
