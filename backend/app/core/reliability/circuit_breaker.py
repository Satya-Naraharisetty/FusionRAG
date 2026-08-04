import asyncio
import time
from collections.abc import Callable
from typing import Any


class CircuitBreakerOpenException(Exception):
    """Exception raised when the circuit breaker is in the OPEN state."""

    pass


class CircuitBreaker:
    def __init__(
        self, failure_threshold: int = 5, recovery_timeout: float = 30.0
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failure_count = 0
        self.last_state_change = time.time()
        self._lock = asyncio.Lock()

    async def record_success(self) -> None:
        async with self._lock:
            self.failure_count = 0
            self.state = "CLOSED"

    async def record_failure(self) -> None:
        async with self._lock:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.last_state_change = time.time()

    async def check_state(self) -> None:
        async with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_state_change > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    self.last_state_change = time.time()
                else:
                    raise CircuitBreakerOpenException(
                        "Circuit breaker is currently OPEN."
                    )

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        await self.check_state()
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            await self.record_success()
            return result
        except Exception as e:
            await self.record_failure()
            raise e
