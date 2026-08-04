from typing import Any

from app.core.cache.interfaces import BaseCache


class BaseCacheRepository:
    def __init__(self, cache: BaseCache, namespace: str, default_ttl: int) -> None:
        self._cache = cache
        self._namespace = namespace
        self._default_ttl = default_ttl

    async def get(self, key: str) -> Any:
        return await self._cache.get(key, namespace=self._namespace)

    async def set(self, key: str, value: Any, ttl: int | None = None, **kwargs: Any) -> None:
        expiration = ttl if ttl is not None else self._default_ttl
        await self._cache.set(key, value, ttl=expiration, namespace=self._namespace, **kwargs)

    async def delete(self, key: str) -> None:
        await self._cache.delete(key, namespace=self._namespace)

    async def invalidate(self) -> None:
        """Clear all keys in this specific namespace."""
        await self._cache.invalidate_namespace(self._namespace)


class PromptCache(BaseCacheRepository):
    def __init__(self, cache: BaseCache) -> None:
        super().__init__(cache, namespace="prompt_rewrite", default_ttl=7200)  # 2 hours


class EmbeddingCache(BaseCacheRepository):
    def __init__(self, cache: BaseCache) -> None:
        super().__init__(cache, namespace="embeddings", default_ttl=86400)  # 24 hours


class ConversationCache(BaseCacheRepository):
    def __init__(self, cache: BaseCache) -> None:
        super().__init__(cache, namespace="conversation_memory", default_ttl=3600)  # 1 hour


class RetrievalCache(BaseCacheRepository):
    def __init__(self, cache: BaseCache) -> None:
        super().__init__(cache, namespace="retrieval_results", default_ttl=1800)  # 30 minutes


class EvaluationCache(BaseCacheRepository):
    def __init__(self, cache: BaseCache) -> None:
        super().__init__(cache, namespace="evaluation_benchmarks", default_ttl=3600)  # 1 hour


class ToolResultCache(BaseCacheRepository):
    def __init__(self, cache: BaseCache) -> None:
        super().__init__(cache, namespace="tool_executions", default_ttl=600)  # 10 minutes
