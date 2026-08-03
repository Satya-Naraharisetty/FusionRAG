import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Optional

import redis


class BaseDistributedLock(ABC):
    @abstractmethod
    async def acquire(
        self, lock_name: str, timeout: float = 10.0, retry_interval: float = 0.1
    ) -> bool:
        """Acquire a distributed lock with a timeout."""
        pass

    @abstractmethod
    async def release(self, lock_name: str) -> None:
        """Release the lock."""
        pass


class RedisDistributedLock(BaseDistributedLock):
    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client
        self._lock_id = str(uuid.uuid4())

    async def acquire(
        self, lock_name: str, timeout: float = 10.0, retry_interval: float = 0.1
    ) -> bool:
        key = f"lock:{lock_name}"
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                # Set key if not exists (nx=True) with a safety expiration (ex=seconds)
                # timeout acts as the lease duration
                res = self._redis.set(
                    key, self._lock_id, nx=True, ex=max(1, int(timeout))
                )
                if res:
                    return True
            except Exception:
                pass
            await asyncio.sleep(retry_interval)
        return False

    async def release(self, lock_name: str) -> None:
        key = f"lock:{lock_name}"
        # Lua script to release the lock only if we own it
        lua_release = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            self._redis.eval(lua_release, 1, key, self._lock_id)
        except Exception:
            pass


class InMemoryDistributedLock(BaseDistributedLock):
    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_owners: Dict[str, str] = {}
        self._global_lock = asyncio.Lock()
        self._lock_id = str(uuid.uuid4())

    async def acquire(
        self, lock_name: str, timeout: float = 10.0, retry_interval: float = 0.1
    ) -> bool:
        async with self._global_lock:
            if lock_name not in self._locks:
                self._locks[lock_name] = asyncio.Lock()
        
        lock = self._locks[lock_name]
        try:
            # Attempt to acquire lock using wait_for timeout
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
            self._lock_owners[lock_name] = self._lock_id
            return True
        except (asyncio.TimeoutError, Exception):
            return False

    async def release(self, lock_name: str) -> None:
        async with self._global_lock:
            if lock_name in self._locks:
                lock = self._locks[lock_name]
                # Only release if we own it and it is locked
                if self._lock_owners.get(lock_name) == self._lock_id and lock.locked():
                    lock.release()
                    self._lock_owners.pop(lock_name, None)
