from unittest.mock import AsyncMock

import pytest

from app.core.queue.redis_queue import RedisStreamTaskQueue


@pytest.mark.asyncio
async def test_retry_pump_lua_script_invocation():
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = 2

    queue = RedisStreamTaskQueue(
        redis_client=mock_redis,
        stream_name="test_stream",
        retry_sorted_set="test_retry_zset",
        max_stream_length=5000,
    )

    pumped = await queue.pump_scheduled_retries(now_ts=1700000000.0, limit=10)

    assert pumped == 2
    mock_redis.eval.assert_called_once()
    args = mock_redis.eval.call_args[0]
    # Check script, numkeys, and arguments
    assert "ZRANGEBYSCORE" in args[0]
    assert "XADD" in args[0]
    assert "ZREM" in args[0]
    assert args[1] == 2
    assert args[2] == "test_retry_zset"
    assert args[3] == "test_stream"
    assert args[4] == "1700000000.0"
    assert args[5] == "10"
    assert args[6] == "5000"
