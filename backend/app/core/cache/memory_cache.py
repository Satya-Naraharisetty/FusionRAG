import asyncio
import time
from typing import Any, Dict, Optional, Set, Tuple

from app.core.cache.interfaces import BaseCache


class InMemoryCache(BaseCache):
    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[Optional[float], Any]] = {}
        self._namespace_keys: Dict[str, Set[str]] = {}
        self._user_keys: Dict[str, Set[str]] = {}
        self._document_keys: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()

    def _get_namespaced_key(self, key: str, namespace: Optional[str] = None) -> str:
        if namespace:
            return f"{namespace}:{key}"
        return key

    async def get(self, key: str, namespace: Optional[str] = None) -> Any:
        async with self._lock:
            full_key = self._get_namespaced_key(key, namespace)
            if full_key not in self._cache:
                return None

            expiry, value = self._cache[full_key]
            if expiry is not None and time.time() > expiry:
                # Lazy eviction
                await self._delete_no_lock(full_key, namespace)
                return None

            return value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        namespace: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        async with self._lock:
            full_key = self._get_namespaced_key(key, namespace)
            expiry = time.time() + ttl if ttl is not None else None
            self._cache[full_key] = (expiry, value)

            # Index by namespace
            if namespace:
                if namespace not in self._namespace_keys:
                    self._namespace_keys[namespace] = set()
                self._namespace_keys[namespace].add(full_key)

            # Index by user
            user_id = kwargs.get("user_id")
            if not user_id:
                # Try context var lookup
                try:
                    from app.core.context.request_context import current_request_context
                    ctx = current_request_context.get()
                    user_id = ctx.user_id
                except Exception:
                    pass

            if user_id:
                user_str = str(user_id)
                if user_str not in self._user_keys:
                    self._user_keys[user_str] = set()
                self._user_keys[user_str].add(full_key)

            # Index by document
            document_id = kwargs.get("document_id")
            if document_id:
                doc_str = str(document_id)
                if doc_str not in self._document_keys:
                    self._document_keys[doc_str] = set()
                self._document_keys[doc_str].add(full_key)

    async def delete(self, key: str, namespace: Optional[str] = None) -> None:
        async with self._lock:
            full_key = self._get_namespaced_key(key, namespace)
            await self._delete_no_lock(full_key, namespace)

    async def _delete_no_lock(self, full_key: str, namespace: Optional[str]) -> None:
        if full_key in self._cache:
            del self._cache[full_key]

        # Clean from namespace index
        if namespace and namespace in self._namespace_keys:
            self._namespace_keys[namespace].discard(full_key)

        # Clean from user index
        for user_id, keys in list(self._user_keys.items()):
            keys.discard(full_key)
            if not keys:
                del self._user_keys[user_id]

        # Clean from document index
        for doc_id, keys in list(self._document_keys.items()):
            keys.discard(full_key)
            if not keys:
                del self._document_keys[doc_id]

    async def invalidate_namespace(self, namespace: str) -> None:
        async with self._lock:
            if namespace in self._namespace_keys:
                keys_to_delete = list(self._namespace_keys[namespace])
                for k in keys_to_delete:
                    # We pass None because full_key is already namespaced and we delete it directly
                    await self._delete_no_lock(k, namespace=None)
                del self._namespace_keys[namespace]

    async def invalidate_user(self, user_id: str) -> None:
        async with self._lock:
            user_str = str(user_id)
            if user_str in self._user_keys:
                keys_to_delete = list(self._user_keys[user_str])
                for k in keys_to_delete:
                    await self._delete_no_lock(k, namespace=None)
                self._user_keys.pop(user_str, None)

    async def invalidate_document(self, document_id: str) -> None:
        async with self._lock:
            doc_str = str(document_id)
            if doc_str in self._document_keys:
                keys_to_delete = list(self._document_keys[doc_str])
                for k in keys_to_delete:
                    await self._delete_no_lock(k, namespace=None)
                self._document_keys.pop(doc_str, None)
