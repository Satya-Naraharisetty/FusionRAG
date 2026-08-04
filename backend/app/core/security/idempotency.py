import json
import logging
from typing import Any

import redis

logger = logging.getLogger(__name__)


class IdempotencyConflictError(Exception):
    """Exception raised when an operation with the same key is already in progress."""

    pass


class IdempotencyManager:
    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client

    def _get_lock_key(self, key: str) -> str:
        return f"lock:idem:{key}"

    def _get_response_key(self, key: str) -> str:
        return f"response:idem:{key}"

    async def check_idempotency(self, key: str) -> Any | None:
        """
        Check if an idempotency key has a cached response, or acquire an in-progress lock.
        Returns the cached response if available.
        Raises IdempotencyConflictError if another worker is already processing it.
        """
        lock_key = self._get_lock_key(key)
        resp_key = self._get_response_key(key)

        try:
            # 1. Check if we already have the completed response
            cached_resp = self._redis.get(resp_key)
            if cached_resp is not None:
                return json.loads(cached_resp)

            # 2. Try to acquire the execution lock (expires in 60s to prevent deadlocks)
            acquired = self._redis.set(lock_key, "processing", nx=True, ex=60)
            if not acquired:
                raise IdempotencyConflictError(
                    "Request with this idempotency key is already in progress."
                )
        except IdempotencyConflictError as e:
            raise e
        except Exception as e:
            logger.error(f"Error checking idempotency for key {key}: {e}")

        return None

    async def save_response(self, key: str, response: Any, ttl: int = 86400) -> None:
        """Save the completed response and release the execution lock."""
        lock_key = self._get_lock_key(key)
        resp_key = self._get_response_key(key)
        serialized = json.dumps(response)

        try:
            pipe = self._redis.pipeline()
            pipe.setex(resp_key, ttl, serialized)
            pipe.delete(lock_key)
            pipe.execute()
        except Exception as e:
            logger.error(f"Error saving idempotency response for key {key}: {e}")

    async def release_lock(self, key: str) -> None:
        """Release the lock manually (called on failures to allow retrying)."""
        lock_key = self._get_lock_key(key)
        try:
            self._redis.delete(lock_key)
        except Exception as e:
            logger.error(f"Error releasing idempotency lock for key {key}: {e}")
