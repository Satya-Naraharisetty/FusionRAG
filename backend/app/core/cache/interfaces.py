from abc import ABC, abstractmethod
from typing import Any


class BaseCache(ABC):
    @abstractmethod
    async def get(self, key: str, namespace: str | None = None) -> Any:
        """Retrieve a value from the cache."""
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        namespace: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Store a value in the cache with an optional TTL in seconds."""
        pass

    @abstractmethod
    async def delete(self, key: str, namespace: str | None = None) -> None:
        """Delete a key from the cache."""
        pass

    @abstractmethod
    async def invalidate_namespace(self, namespace: str) -> None:
        """Invalidate all keys under a specific namespace."""
        pass

    @abstractmethod
    async def invalidate_user(self, user_id: str) -> None:
        """Invalidate all keys associated with a specific user."""
        pass

    @abstractmethod
    async def invalidate_document(self, document_id: str) -> None:
        """Invalidate all keys associated with a specific document."""
        pass
