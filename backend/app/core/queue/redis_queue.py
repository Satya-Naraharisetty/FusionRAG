import json
import logging
import os
import re
import socket
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import redis.asyncio as async_redis
from redis.exceptions import ResponseError

from app.core.queue.interfaces import DurableTaskQueue, Job

logger = logging.getLogger(__name__)


def generate_consumer_name() -> str:
    """Generates a unique consumer name combining host, PID, and random entropy."""
    host = socket.gethostname()[:16]
    pid = os.getpid()
    entropy = uuid4().hex[:8]
    return f"{host}-{pid}-{entropy}"


def sanitize_error_message(error: str, max_length: int = 1000) -> str:
    """Sanitizes error string by scrubbing potential tokens/secrets and truncating."""
    if not error:
        return ""
    # Scrub common authorization/token patterns
    sanitized = re.sub(r"(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*", r"\1[REDACTED]", error)
    sanitized = re.sub(
        r"(key|secret|password|token)=['\"][^'\"]+['\"]",
        r"\1=[REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized[:max_length]


_LUA_RETRY_PUMP_SCRIPT = """
local items = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, tonumber(ARGV[2]))
local pumped = 0
for i, item in ipairs(items) do
    redis.call('XADD', KEYS[2], 'MAXLEN', '~', tonumber(ARGV[3]), '*', 'data', item)
    redis.call('ZREM', KEYS[1], item)
    pumped = pumped + 1
end
return pumped
"""


class RedisStreamTaskQueue(DurableTaskQueue):
    """
    Durable Task Queue implementation backed by Redis Streams & Consumer Groups.
    Guarantees at-least-once message delivery, worker crash recovery via PEL,
    delayed retries using sorted sets, and dead-letter queue routing.
    """

    def __init__(
        self,
        redis_client: async_redis.Redis,
        stream_name: str = "stream:jobs:document_processing",
        consumer_group: str = "group:document_workers",
        dead_letter_stream: str = "stream:jobs:dead_letter",
        retry_sorted_set: str = "queue:jobs:retry",
        max_stream_length: int = 10000,
        consumer_name: str | None = None,
    ) -> None:
        self._redis = redis_client
        self._stream_name = stream_name
        self._consumer_group = consumer_group
        self._dead_letter_stream = dead_letter_stream
        self._retry_sorted_set = retry_sorted_set
        self._max_stream_length = max_stream_length
        self._consumer_name = consumer_name or generate_consumer_name()

    @property
    def consumer_name(self) -> str:
        return self._consumer_name

    @property
    def stream_name(self) -> str:
        return self._stream_name

    @property
    def consumer_group(self) -> str:
        return self._consumer_group

    async def ensure_consumer_group(self) -> None:
        """
        Idempotently creates the Redis Stream and Consumer Group if it does not exist.
        """
        try:
            await self._redis.xgroup_create(
                name=self._stream_name,
                groupname=self._consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info(
                f"Created consumer group '{self._consumer_group}' on stream '{self._stream_name}'"
            )
        except ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.debug(
                    f"Consumer group '{self._consumer_group}' already exists on stream '{self._stream_name}'"
                )
            else:
                raise

    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        max_attempts: int = 3,
        correlation_id: str | None = None,
        job_id: UUID | None = None,
    ) -> Job:
        """
        Enqueues a job onto the Redis Stream.
        Serializes strictly metadata — never raw binaries or Python callables.
        """
        job = Job(
            job_id=job_id or uuid4(),
            task_type=task_type,
            payload=payload,
            attempt=1,
            max_attempts=max_attempts,
            created_at=datetime.now(UTC),
            correlation_id=correlation_id,
        )

        job_data = job.model_dump_json_safe()
        serialized = json.dumps(job_data)

        msg_id = await self._redis.xadd(
            name=self._stream_name,
            fields={"data": serialized},
            maxlen=self._max_stream_length,
            approximate=True,
        )
        msg_id_str = (
            msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
        )

        logger.info(
            f"queue.job_enqueued: job_id={job.job_id} task_type={job.task_type} "
            f"stream_msg_id={msg_id_str} attempt={job.attempt}/{job.max_attempts} "
            f"correlation_id={job.correlation_id}"
        )
        return job

    async def acknowledge(self, stream_message_id: str | UUID) -> None:
        """
        Acknowledges a message in the consumer group (XACK).
        """
        msg_id_str = str(stream_message_id)
        await self._redis.xack(self._stream_name, self._consumer_group, msg_id_str)

    async def reject(self, job_id: UUID, error: str, retryable: bool = True) -> None:
        """
        Rejects a job. For Redis Streams, granular message rejection is handled
        via schedule_retry or route_to_dead_letter combined with XACK.
        """
        logger.warning(
            f"queue.job_rejected: job_id={job_id} retryable={retryable} error={error}"
        )

    async def schedule_retry(self, job: Job, error: str, delay_seconds: float) -> None:
        """
        Schedules a failed job for retry with exponential backoff via a sorted set.
        """
        job.attempt += 1
        next_attempt_at = time.time() + max(0.1, delay_seconds)
        job_data = job.model_dump_json_safe()
        serialized = json.dumps(job_data)

        await self._redis.zadd(self._retry_sorted_set, {serialized: next_attempt_at})
        logger.info(
            f"queue.job_retried: job_id={job.job_id} task_type={job.task_type} "
            f"next_attempt={job.attempt}/{job.max_attempts} backoff_delay_s={delay_seconds:.2f} "
            f"error={sanitize_error_message(error, 200)}"
        )

    async def route_to_dead_letter(
        self, job: Job, error: str, error_type: str | None = None
    ) -> None:
        """
        Routes an unrecoverable or retry-exhausted job to the Dead-Letter Stream.
        """
        sanitized = sanitize_error_message(error)
        dlq_entry = {
            "job_id": str(job.job_id),
            "task_type": job.task_type,
            "attempt": job.attempt,
            "max_attempts": job.max_attempts,
            "error_type": error_type or "NonRetryableFailure",
            "sanitized_error": sanitized,
            "created_at": job.created_at.isoformat(),
            "dead_lettered_at": datetime.now(UTC).isoformat(),
            "correlation_id": job.correlation_id,
            "payload": job.payload,
        }
        serialized = json.dumps(dlq_entry)

        await self._redis.xadd(
            name=self._dead_letter_stream,
            fields={"data": serialized},
            maxlen=self._max_stream_length,
            approximate=True,
        )

        logger.error(
            f"queue.job_dead_lettered: job_id={job.job_id} task_type={job.task_type} "
            f"final_attempt={job.attempt}/{job.max_attempts} error_type={error_type} "
            f"error={sanitized[:200]}"
        )

    async def read_messages(
        self, count: int = 10, block_ms: int = 2000
    ) -> list[tuple[str, Job]]:
        """
        Reads newly enqueued messages from the consumer group using XREADGROUP.
        """
        try:
            raw_entries: Any = await self._redis.xreadgroup(
                groupname=self._consumer_group,
                consumername=self._consumer_name,
                streams={self._stream_name: ">"},
                count=count,
                block=block_ms,
            )
        except Exception as e:
            logger.error(f"Error reading from Redis stream {self._stream_name}: {e}")
            return []

        jobs: list[tuple[str, Job]] = []
        if not raw_entries or not isinstance(raw_entries, list):
            return jobs

        for stream_tuple in raw_entries:
            if not isinstance(stream_tuple, (list, tuple)) or len(stream_tuple) < 2:
                continue
            msg_list = stream_tuple[1]
            if not isinstance(msg_list, list):
                continue

            for msg_tuple in msg_list:
                if not isinstance(msg_tuple, (list, tuple)) or len(msg_tuple) < 2:
                    continue
                msg_id = msg_tuple[0]
                fields = msg_tuple[1]
                if not isinstance(fields, dict):
                    continue

                msg_id_str = (
                    msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
                )
                data_field = (
                    fields.get(b"data") if b"data" in fields else fields.get("data")
                )
                if not data_field:
                    logger.warning(
                        f"Malformed stream entry {msg_id_str}: missing 'data' field. Discarding."
                    )
                    await self.acknowledge(msg_id_str)
                    continue

                try:
                    raw_str = (
                        data_field.decode("utf-8")
                        if isinstance(data_field, bytes)
                        else str(data_field)
                    )
                    parsed = json.loads(raw_str)
                    job = Job.from_dict(parsed)
                    jobs.append((msg_id_str, job))
                except Exception as ex:
                    logger.error(
                        f"Failed to deserialize stream job {msg_id_str}: {ex}. Discarding."
                    )
                    await self.acknowledge(msg_id_str)

        return jobs

    async def reclaim_orphaned_jobs(
        self, min_idle_time_ms: int = 60000, count: int = 10, start_id: str = "0-0"
    ) -> tuple[str, list[tuple[str, Job]]]:
        """
        Reclaims orphaned pending messages using XAUTOCLAIM.
        Used for worker crash recovery.
        """
        try:
            # xautoclaim returns (next_start_id, list_of_messages, [deleted_message_ids])
            result: Any = await self._redis.xautoclaim(
                name=self._stream_name,
                groupname=self._consumer_group,
                consumername=self._consumer_name,
                min_idle_time=min_idle_time_ms,
                start_id=start_id,
                count=count,
            )
        except Exception as e:
            logger.error(f"Error executing XAUTOCLAIM on {self._stream_name}: {e}")
            return ("0-0", [])

        if not isinstance(result, (list, tuple)) or len(result) < 2:
            return ("0-0", [])

        next_start_id = result[0]
        if isinstance(next_start_id, bytes):
            next_id_str = next_start_id.decode("utf-8")
        else:
            next_id_str = str(next_start_id)

        claimed_entries = result[1]
        reclaimed_jobs: list[tuple[str, Job]] = []

        if isinstance(claimed_entries, list):
            for entry in claimed_entries:
                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue
                msg_id = entry[0]
                fields = entry[1]
                if not isinstance(fields, dict):
                    continue

                msg_id_str = (
                    msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
                )
                data_field = (
                    fields.get(b"data") if b"data" in fields else fields.get("data")
                )
                if not data_field:
                    await self.acknowledge(msg_id_str)
                    continue

                try:
                    raw_str = (
                        data_field.decode("utf-8")
                        if isinstance(data_field, bytes)
                        else str(data_field)
                    )
                    parsed = json.loads(raw_str)
                    job = Job.from_dict(parsed)
                    reclaimed_jobs.append((msg_id_str, job))
                    logger.info(
                        f"queue.job_reclaimed: job_id={job.job_id} stream_msg_id={msg_id_str} "
                        f"by_consumer={self._consumer_name}"
                    )
                except Exception as ex:
                    logger.error(
                        f"Failed to deserialize reclaimed job {msg_id_str}: {ex}"
                    )
                    await self.acknowledge(msg_id_str)

        return (next_id_str, reclaimed_jobs)

    async def pump_scheduled_retries(
        self, now_ts: float | None = None, limit: int = 50
    ) -> int:
        """
        Transfers due retry jobs from the sorted set back into the main stream (XADD)
        atomically using a Redis Lua script. Enforces the durability invariant that
        a retry item is appended to the stream before it is removed from the ZSET.
        """
        current_time = now_ts if now_ts is not None else time.time()
        try:
            result = await self._redis.eval(
                _LUA_RETRY_PUMP_SCRIPT,
                2,
                self._retry_sorted_set,
                self._stream_name,
                str(current_time),
                str(limit),
                str(self._max_stream_length),
            )
            pumped = int(result or 0)
            if pumped > 0:
                logger.info(f"queue.retries_pumped: count={pumped}")
            return pumped
        except Exception as e:
            logger.error(f"Failed to execute atomic retry pump Lua script: {e}")
            raise
