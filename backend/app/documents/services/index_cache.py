import collections
import threading
import time
from typing import Any, Set
from uuid import UUID

from app.core.config import settings
from app.documents.domain.interfaces import IndexCache


class InMemoryIndexCache(IndexCache):
    def __init__(self, max_capacity: int | None = None) -> None:
        self._lock = threading.Lock()
        # If max_capacity is not specified, read it from settings
        self.max_capacity = max_capacity if max_capacity is not None else settings.INDEX_CACHE_MAX_USERS
        if self.max_capacity <= 0:
            raise ValueError("Cache capacity must be greater than zero.")
        # Structure: user_id -> {"index_data": Any, "stats": dict[str, Any], "created_at": float}
        # Using OrderedDict to implement LRU policy
        self._cache: collections.OrderedDict[UUID, dict[str, Any]] = collections.OrderedDict()

    def get(self, user_id: UUID) -> Any | None:
        with self._lock:
            entry = self._cache.get(user_id)
            if entry:
                # Update recency: move to end
                self._cache.move_to_end(user_id)
                return entry["index_data"]
            return None

    def set(self, user_id: UUID, index_data: Any, stats: dict[str, Any]) -> None:
        with self._lock:
            # If entry already exists, update it and move to end
            if user_id in self._cache:
                self._cache[user_id] = {
                    "index_data": index_data,
                    "stats": stats,
                    "created_at": time.monotonic(),
                }
                self._cache.move_to_end(user_id)
            else:
                # Evict oldest entry (the first one) if at capacity
                while len(self._cache) >= self.max_capacity:
                    self._cache.popitem(last=False)
                
                self._cache[user_id] = {
                    "index_data": index_data,
                    "stats": stats,
                    "created_at": time.monotonic(),
                }

    def get_stats(self, user_id: UUID) -> dict[str, Any] | None:
        with self._lock:
            entry = self._cache.get(user_id)
            if entry:
                # Update recency: move to end
                self._cache.move_to_end(user_id)
                return entry["stats"]
            return None

    def get_fresh_stats(
        self, user_id: UUID, max_age_seconds: float
    ) -> dict[str, Any] | None:
        """
        Returns the user's stats only when the cache entry was created within
        the last ``max_age_seconds``, else None. Expired entries are treated
        as missing (but not evicted) so callers re-check their source of truth
        without disturbing the long-lived BM25 index data.
        """
        with self._lock:
            entry = self._cache.get(user_id)
            if not entry:
                return None
            
            # Update recency since it was accessed
            self._cache.move_to_end(user_id)
            
            if time.monotonic() - entry["created_at"] > max_age_seconds:
                return None
            return entry["stats"]

    def invalidate(self, user_id: UUID) -> None:
        with self._lock:
            if user_id in self._cache:
                del self._cache[user_id]

    def get_cached_user_ids(self) -> Set[UUID]:
        with self._lock:
            return set(self._cache.keys())
