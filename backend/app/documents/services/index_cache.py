import threading
from typing import Any
from uuid import UUID

from app.documents.domain.interfaces import IndexCache


class InMemoryIndexCache(IndexCache):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Structure: user_id -> {"index_data": Any, "stats": dict[str, Any]}
        self._cache = {}

    def get(self, user_id: UUID) -> Any | None:
        with self._lock:
            entry = self._cache.get(user_id)
            return entry["index_data"] if entry else None

    def set(self, user_id: UUID, index_data: Any, stats: dict[str, Any]) -> None:
        with self._lock:
            self._cache[user_id] = {
                "index_data": index_data,
                "stats": stats,
            }

    def get_stats(self, user_id: UUID) -> dict[str, Any] | None:
        with self._lock:
            entry = self._cache.get(user_id)
            return entry["stats"] if entry else None

    def invalidate(self, user_id: UUID) -> None:
        with self._lock:
            if user_id in self._cache:
                del self._cache[user_id]
