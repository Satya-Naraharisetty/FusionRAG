from app.chat.domain.interfaces import HistoryRewriteCache


class MemoryRewriteCache(HistoryRewriteCache):
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._cache.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._cache[key] = value


class RedisRewriteCache(HistoryRewriteCache):
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def get(self, key: str) -> str | None:
        if not self._redis:
            return None
        try:
            val = self._redis.get(key)
            if val:
                return val.decode("utf-8") if isinstance(val, bytes) else str(val)
        except Exception:
            pass
        return None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if not self._redis:
            return
        try:
            self._redis.setex(key, ttl_seconds, value)
        except Exception:
            pass
