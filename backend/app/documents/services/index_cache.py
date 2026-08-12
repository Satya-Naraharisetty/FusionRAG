import threading
import time
from typing import Any
from uuid import UUID

from app.documents.domain.interfaces import IndexCache


class InMemoryIndexCache(IndexCache):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Structure: user_id -> {"index_data": Any, "stats": dict[str, Any], "created_at": float}
        self._cache: dict[UUID, dict[str, Any]] = {}

    def get(self, user_id: UUID) -> Any | None:
        with self._lock:
            entry = self._cache.get(user_id)
            return entry["index_data"] if entry else None

    def set(self, user_id: UUID, index_data: Any, stats: dict[str, Any]) -> None:
        with self._lock:
            self._cache[user_id] = {
                "index_data": index_data,
                "stats": stats,
                "created_at": time.monotonic(),
            }

    def get_stats(self, user_id: UUID) -> dict[str, Any] | None:
        with self._lock:
            entry = self._cache.get(user_id)
            return entry["stats"] if entry else None

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
            if time.monotonic() - entry["created_at"] > max_age_seconds:
                return None
            return entry["stats"]

    def invalidate(self, user_id: UUID) -> None:
        with self._lock:
            if user_id in self._cache:
                del self._cache[user_id]
