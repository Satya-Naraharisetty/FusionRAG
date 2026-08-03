import asyncio
import functools
import random
from typing import Any, Callable, Tuple, Type, Union


async def retry_with_backoff(
    func: Callable,
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    factor: float = 2.0,
    retry_on_exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    **kwargs: Any,
) -> Any:
    """Execute a function with exponential backoff retry and full jitter."""
    for attempt in range(max_attempts):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except retry_on_exceptions as e:
            if attempt == max_attempts - 1:
                raise e
            # Apply Full Jitter: sleep = random.uniform(0, min(max_delay, base_delay * (factor ** attempt)))
            delay = random.uniform(0, min(max_delay, base_delay * (factor ** attempt)))
            await asyncio.sleep(delay)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    factor: float = 2.0,
    retry_on_exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
):
    """Decorator to retry a function with exponential backoff and full jitter."""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await retry_with_backoff(
                func,
                *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                factor=factor,
                retry_on_exceptions=retry_on_exceptions,
                **kwargs,
            )
        return wrapper
    return decorator
