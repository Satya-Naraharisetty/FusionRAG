import asyncio
from typing import Any, Dict


class BulkheadFullException(Exception):
    """Exception raised when a bulkhead resource queue is full."""
    pass


class Bulkhead:
    def __init__(self, semaphore: asyncio.Semaphore, name: str) -> None:
        self._semaphore = semaphore
        self._name = name

    async def __aenter__(self) -> None:
        # Fail-fast: if the semaphore has no slots available, reject immediately
        if self._semaphore.locked():
            raise BulkheadFullException(
                f"Concurrency limit reached for resource bulkhead '{self._name}'."
            )
        await self._semaphore.acquire()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._semaphore.release()


class BulkheadManager:
    def __init__(self) -> None:
        self._semaphores: Dict[str, asyncio.Semaphore] = {
            "llm": asyncio.Semaphore(50),
            "embedding": asyncio.Semaphore(30),
            "evaluation": asyncio.Semaphore(5),  # CPU/heavy benchmark limit
            "retrieval": asyncio.Semaphore(100),
            "storage": asyncio.Semaphore(20),
        }

    def get_semaphore(self, resource_name: str) -> asyncio.Semaphore:
        normalized_name = resource_name.lower()
        if normalized_name not in self._semaphores:
            self._semaphores[normalized_name] = asyncio.Semaphore(10)  # Default fallback
        return self._semaphores[normalized_name]

    def acquire_bulkhead(self, resource_name: str) -> Bulkhead:
        sem = self.get_semaphore(resource_name)
        return Bulkhead(sem, resource_name)


# Global singleton manager
bulkhead_manager = BulkheadManager()
