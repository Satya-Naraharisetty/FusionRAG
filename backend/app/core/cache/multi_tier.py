from typing import Any

from app.core.cache.interfaces import BaseCache
from app.core.cache.memory_cache import InMemoryCache
from app.core.cache.redis_cache import RedisCache


class MultiTierCache(BaseCache):
    def __init__(self, l1_cache: InMemoryCache, l2_cache: RedisCache) -> None:
        self.l1 = l1_cache
        self.l2 = l2_cache

    async def get(self, key: str, namespace: str | None = None) -> Any:
        # 1. Probe L1 Memory Cache
        val = await self.l1.get(key, namespace)
        if val is not None:
            return val

        # 2. Probe L2 Redis Cache
        val = await self.l2.get(key, namespace)
        if val is not None:
            # Sync back to L1 with a short L1 TTL (e.g., 5 mins / 300s) to keep memory footprint low
            await self.l1.set(key, val, ttl=300, namespace=namespace)
            return val

        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        namespace: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Write to both L1 and L2
        await self.l1.set(key, value, ttl=ttl, namespace=namespace, **kwargs)
        await self.l2.set(key, value, ttl=ttl, namespace=namespace, **kwargs)

    async def delete(self, key: str, namespace: str | None = None) -> None:
        # Delete from both L1 and L2
        await self.l1.delete(key, namespace)
        await self.l2.delete(key, namespace)

    async def invalidate_namespace(self, namespace: str) -> None:
        await self.l1.invalidate_namespace(namespace)
        await self.l2.invalidate_namespace(namespace)

    async def invalidate_user(self, user_id: str) -> None:
        await self.l1.invalidate_user(user_id)
        await self.l2.invalidate_user(user_id)

    async def invalidate_document(self, document_id: str) -> None:
        await self.l1.invalidate_document(document_id)
        await self.l2.invalidate_document(document_id)
