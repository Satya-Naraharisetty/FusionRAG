from app.core.queue.retry import calculate_backoff


def test_calculate_backoff_first_attempt():
    # Attempt 1: 2.0 * (2^0) = 2.0. Jitter is in [0.5, 1.0], so delay in [1.0, 2.0]
    delay = calculate_backoff(1, base_delay=2.0, max_delay=60.0)
    assert 1.0 <= delay <= 2.0


def test_calculate_backoff_exponential_growth():
    # Deterministic test with injected rng_func returning 1.0 (max jitter)
    def rng_max() -> float:
        return 1.0

    d1 = calculate_backoff(1, base_delay=2.0, max_delay=60.0, rng_func=rng_max)
    d2 = calculate_backoff(2, base_delay=2.0, max_delay=60.0, rng_func=rng_max)
    d3 = calculate_backoff(3, base_delay=2.0, max_delay=60.0, rng_func=rng_max)
    d4 = calculate_backoff(4, base_delay=2.0, max_delay=60.0, rng_func=rng_max)

    assert d1 == 2.0
    assert d2 == 4.0
    assert d3 == 8.0
    assert d4 == 16.0


def test_calculate_backoff_max_delay_cap():
    def rng_max() -> float:
        return 1.0

    # Attempt 10 would be 2 * 2^9 = 1024, capped at max_delay = 30.0
    delay = calculate_backoff(10, base_delay=2.0, max_delay=30.0, rng_func=rng_max)
    assert delay == 30.0


def test_calculate_backoff_jitter_bounds():
    def rng_min() -> float:
        return 0.5

    def rng_max() -> float:
        return 1.0

    delay_min = calculate_backoff(3, base_delay=2.0, max_delay=60.0, rng_func=rng_min)
    delay_max = calculate_backoff(3, base_delay=2.0, max_delay=60.0, rng_func=rng_max)

    # 2 * 2^2 = 8.0. Min is 8 * 0.5 = 4.0; Max is 8 * 1.0 = 8.0
    assert delay_min == 4.0
    assert delay_max == 8.0


def test_calculate_backoff_negative_or_zero_attempt():
    delay = calculate_backoff(0, base_delay=2.0, max_delay=60.0)
    assert 1.0 <= delay <= 2.0
