import json
import logging
from typing import Any

import redis.asyncio as async_redis

from app.core.cache.interfaces import BaseCache

logger = logging.getLogger(__name__)


class RedisCache(BaseCache):
    def __init__(self, redis_client: async_redis.Redis) -> None:
        self._redis = redis_client

    def _get_namespaced_key(self, key: str, namespace: str | None = None) -> str:
        if namespace:
            return f"ns:{namespace}:{key}"
        return key

    async def get(self, key: str, namespace: str | None = None) -> Any:
        full_key = self._get_namespaced_key(key, namespace)
        try:
            val = await self._redis.get(full_key)
            if val is not None:
                return json.loads(val)
        except Exception as e:
            logger.error(f"Redis get failed for key {full_key}: {e}")
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        namespace: str | None = None,
        **kwargs: Any,
    ) -> None:
        full_key = self._get_namespaced_key(key, namespace)
        serialized = json.dumps(value)
        try:
            async with self._redis.pipeline() as pipe:
                # Save actual value
                if ttl is not None:
                    pipe.setex(full_key, ttl, serialized)
                else:
                    pipe.set(full_key, serialized)

                # Track key under namespace
                if namespace:
                    ns_set = f"idx:ns:{namespace}:keys"
                    pipe.sadd(ns_set, full_key)
                    pipe.expire(ns_set, 86400 * 7)  # Index expires in 7 days

                # Track key under user
                user_id = kwargs.get("user_id")
                if not user_id:
                    try:
                        from app.core.context.request_context import (
                            current_request_context,
                        )

                        ctx = current_request_context.get()
                        user_id = ctx.user_id
                    except Exception:
                        pass

                if user_id:
                    user_str = str(user_id)
                    user_set = f"idx:user:{user_str}:keys"
                    pipe.sadd(user_set, full_key)
                    pipe.expire(user_set, 86400 * 7)

                # Track key under document
                document_id = kwargs.get("document_id")
                if document_id:
                    doc_str = str(document_id)
                    doc_set = f"idx:doc:{doc_str}:keys"
                    pipe.sadd(doc_set, full_key)
                    pipe.expire(doc_set, 86400 * 7)

                await pipe.execute()
        except Exception as e:
            logger.error(f"Redis set failed for key {full_key}: {e}")

    async def delete(self, key: str, namespace: str | None = None) -> None:
        full_key = self._get_namespaced_key(key, namespace)
        try:
            await self._redis.delete(full_key)
        except Exception as e:
            logger.error(f"Redis delete failed for key {full_key}: {e}")

    async def invalidate_namespace(self, namespace: str) -> None:
        ns_set = f"idx:ns:{namespace}:keys"
        try:
            keys = await self._redis.smembers(ns_set)
            if keys:
                async with self._redis.pipeline() as pipe:
                    for key in keys:
                        pipe.delete(key)
                    pipe.delete(ns_set)
                    await pipe.execute()
        except Exception as e:
            logger.error(f"Redis namespace invalidation failed for {namespace}: {e}")

    async def invalidate_user(self, user_id: str) -> None:
        user_str = str(user_id)
        user_set = f"idx:user:{user_str}:keys"
        try:
            keys = await self._redis.smembers(user_set)
            if keys:
                async with self._redis.pipeline() as pipe:
                    for key in keys:
                        pipe.delete(key)
                    pipe.delete(user_set)
                    await pipe.execute()
        except Exception as e:
            logger.error(f"Redis user invalidation failed for {user_id}: {e}")

    async def invalidate_document(self, document_id: str) -> None:
        doc_str = str(document_id)
        doc_set = f"idx:doc:{doc_str}:keys"
        try:
            keys = await self._redis.smembers(doc_set)
            if keys:
                async with self._redis.pipeline() as pipe:
                    for key in keys:
                        pipe.delete(key)
                    pipe.delete(doc_set)
                    await pipe.execute()
        except Exception as e:
            logger.error(f"Redis document invalidation failed for {document_id}: {e}")
