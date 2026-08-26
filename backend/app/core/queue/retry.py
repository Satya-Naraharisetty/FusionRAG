import random
from collections.abc import Callable


def calculate_backoff(
    attempt: int,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    rng_func: Callable[[], float] | None = None,
) -> float:
    """
    Calculates exponential backoff with full jitter.

    Formula:
      ceiling = min(max_delay, base_delay * (2 ** (attempt - 1)))
      delay = ceiling * jitter (where jitter is uniformly distributed in [0.5, 1.0])

    Allows injecting rng_func for deterministic unit testing.
    """
    if attempt < 1:
        attempt = 1
    ceiling = min(max_delay, base_delay * (2 ** (attempt - 1)))
    jitter = rng_func() if rng_func is not None else random.uniform(0.5, 1.0)
    delay = ceiling * jitter
    return max(0.1, min(max_delay, delay))
