import asyncio
import functools
from collections.abc import Callable
from typing import Any


class TimeoutException(Exception):
    """Exception raised when an operation exceeds its configured timeout duration."""
    pass


async def timeout_policy(
    func: Callable, timeout_seconds: float, *args: Any, **kwargs: Any
) -> Any:
    """Execute a callable and raise TimeoutException if timeout_seconds is exceeded."""
    try:
        if asyncio.iscoroutinefunction(func):
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
        else:
            return await asyncio.wait_for(
                asyncio.to_thread(func, *args, **kwargs), timeout=timeout_seconds
            )
    except TimeoutError as e:
        raise TimeoutException(
            f"Operation timed out after {timeout_seconds} seconds."
        ) from e


def with_timeout(timeout_seconds: float):
    """Decorator to enforce a execution timeout on an async function."""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await timeout_policy(func, timeout_seconds, *args, **kwargs)
        return wrapper
    return decorator
