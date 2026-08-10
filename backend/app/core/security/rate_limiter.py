import logging
import threading
import time

import redis

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        requests_per_minute: int = 60,
        burst: int = 10,
    ) -> None:
        self._redis = redis_client
        self.requests_per_minute = requests_per_minute
        self.burst = burst
        self._memory_db: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    async def is_rate_limited(self, identifier: str) -> bool:
        """
        Check if the identifier (IP or User ID) has exceeded the rate limit.
        Returns True if rate limited (blocked), False otherwise.
        """
        if self._redis:
            try:
                now = time.time()
                window_start = now - 60.0
                key = f"rate:limit:{identifier}"

                pipe = self._redis.pipeline()
                # 1. Clean up old requests from sliding window
                pipe.zremrangebyscore(key, 0, window_start)
                # 2. Count active request timestamps
                pipe.zcard(key)
                # 3. Add current timestamp
                pipe.zadd(key, {str(now): now})
                # 4. Refresh key TTL
                pipe.expire(key, 60)

                _, count, _, _ = pipe.execute()

                # Block when the window is already full (>=), matching the
                # in-memory fallback so both paths allow exactly
                # requests_per_minute + burst requests per window.
                if count >= (self.requests_per_minute + self.burst):
                    return True
                return False
            except Exception as e:
                logger.error(f"Redis rate limiting failed, using memory fallback: {e}")

        # Memory Fallback
        now = time.time()
        window_start = now - 60.0
        with self._lock:
            if identifier not in self._memory_db:
                self._memory_db[identifier] = []

            # Evict timestamps older than 60s
            self._memory_db[identifier] = [
                t for t in self._memory_db[identifier] if t > window_start
            ]

            if len(self._memory_db[identifier]) >= (
                self.requests_per_minute + self.burst
            ):
                return True

            self._memory_db[identifier].append(now)
            return False
