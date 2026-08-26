import logging
import threading
import time

import redis.asyncio as async_redis

logger = logging.getLogger(__name__)

# Per-process shared store for the in-memory fallback, keyed by
# (requests_per_minute, burst) so every RateLimiter instance with the same
# config shares the same sliding-window counters — and the same lock.
# Without this, app/api/dependencies.py built a brand-new limiter (and a
# brand-new dict) for every request, so the fallback counters reset between
# requests and rate limiting silently no-oped whenever Redis was
# unavailable — it only worked in the dockerized stack, where Redis is
# always reachable. Sharing is per process: multi-worker deployments still
# need Redis for cross-process enforcement. Growth is bounded — see
# _MEMORY_PRUNE_INTERVAL and _MEMORY_MAX_IDENTIFIERS below.
_MEMORY_STORES: dict[tuple[int, int, int], dict[str, list[float]]] = {}
_MEMORY_STORE_LOCK = threading.Lock()

# Bounds for the in-memory fallback stores. Without them, identifiers only
# evict when they are seen again, so heavy unique-IP traffic (e.g. a
# distributed attempt to exhaust the fallback while Redis is down) would grow
# a store for the lifetime of the process until it OOMs. Two mechanisms keep
# it bounded, both running under the shared lock when a NEW identifier
# arrives — which is exactly the case where the store can grow:
#   * _MEMORY_PRUNE_INTERVAL: at most once per interval, drop every identifier
#     whose newest timestamp has aged out of the 60s sliding window. A free
#     O(n) sweep that reclaims identifiers which stopped coming back.
#   * _MEMORY_MAX_IDENTIFIERS: if a burst of brand-new identifiers still
#     overshoots this cap between sweeps, evict the least-recently-active
#     identifiers (oldest newest-timestamp first; ties broken by insertion
#     order). This hard-bounds memory even mid-attack. The cap is per store,
#     so it also bounds the per-user delete limiter store — under Redis-down
#     degradation with >MAX distinct users, eviction can reset a user's
#     password-attempt budget mid-guessing-attack; the documented trade-off
#     of a bounded best-effort fallback.
# The deliberate trade-off of eviction: a blocked caller whose identifier is
# evicted gets a fresh window. A bounded best-effort fallback beats an
# unbounded one that can take down the whole process.
_MEMORY_PRUNE_INTERVAL = 60.0
_MEMORY_MAX_IDENTIFIERS = 5000
# Per-config deadline for the next sweep (time.time(), matching the sliding
# window), so each store is swept at most once per _MEMORY_PRUNE_INTERVAL.
_MEMORY_PRUNE_AT: dict[tuple[int, int, int], float] = {}

# Redis-health circuit breaker. The Redis path in is_rate_limited() is a sync
# call with no await, so when Redis is down every rate-limited request used to
# stall for the full socket/DNS timeout (~4s on the dockerized stack) and
# block the async event loop — and because dependencies.py builds a fresh
# limiter per request, a 70-request burst spread over minutes can never fill
# the sliding window (entries keep expiring before the budget is reached).
# After a failed Redis attempt we trip the breaker: for _REDIS_UNHEALTHY_TTL
# seconds the limiter skips Redis entirely and uses the shared in-memory
# fallback directly (microseconds instead of seconds), then the next request
# probes Redis once — so recovery is detected within one TTL. The check-and-set
# has no await, so it is atomic with respect to the event loop.
_REDIS_UNHEALTHY_TTL_SECONDS = 5.0
_redis_unhealthy_until: float = 0.0  # monotonic deadline; 0.0 == healthy


def _trip_redis_breaker() -> None:
    """Open the Redis-health circuit breaker for one TTL window."""
    global _redis_unhealthy_until
    _redis_unhealthy_until = time.monotonic() + _REDIS_UNHEALTHY_TTL_SECONDS


class RateLimiter:
    def __init__(
        self,
        redis_client: async_redis.Redis | None = None,
        requests_per_minute: int = 60,
        burst: int = 10,
        window_seconds: float = 60.0,
    ) -> None:
        self._redis = redis_client
        self.requests_per_minute = requests_per_minute
        self.burst = burst
        self.window_seconds = window_seconds
        # Share the fallback counters with every other limiter using the same
        # (requests_per_minute, burst, window_seconds) config in this process.
        config_key = (requests_per_minute, burst, int(window_seconds))
        self._memory_db = _MEMORY_STORES.setdefault(config_key, {})
        self._lock = _MEMORY_STORE_LOCK

    def _sweep_stale_identifiers(self, now: float, window_start: float) -> None:
        """
        Amortized sweep (called under the shared lock on a new-identifier
        insert): at most once per _MEMORY_PRUNE_INTERVAL per store, drop every
        identifier whose newest timestamp has aged out of the sliding window.
        """
        config_key = (self.requests_per_minute, self.burst, int(self.window_seconds))
        if now < _MEMORY_PRUNE_AT.get(config_key, 0.0):
            return
        _MEMORY_PRUNE_AT[config_key] = now + _MEMORY_PRUNE_INTERVAL
        stale = [
            ident
            for ident, stamps in self._memory_db.items()
            if not stamps or stamps[-1] <= window_start
        ]
        for ident in stale:
            del self._memory_db[ident]

    def _evict_over_cap(self) -> None:
        """
        Hard bound (called under the shared lock after inserting a new
        identifier): if the store exceeds _MEMORY_MAX_IDENTIFIERS, evict the
        least-recently-active identifiers so memory stays bounded even when a
        burst of new identifiers lands between sweeps. A min-loop is O(n) per
        eviction — the common case is a single excess entry under sustained
        unique-IP traffic, so a full sort would be wasteful on the hot path.

        Empty lists rank as most-recent (+inf): the just-inserted identifier
        is never the one evicted. Narrow caveat: an identifier whose timestamps
        all aged out while the sweep is not yet due also has an empty list, so
        it is protected from eviction until the next sweep — the sweep-before-
        insert ordering and insertion-order tie-break keep this from evicting
        a live identifier in practice.
        """
        while len(self._memory_db) > _MEMORY_MAX_IDENTIFIERS:
            oldest = min(
                self._memory_db,
                key=lambda ident: (
                    self._memory_db[ident][-1]
                    if self._memory_db[ident]
                    else float("inf")
                ),
            )
            del self._memory_db[oldest]

    async def is_rate_limited(self, identifier: str) -> bool:
        """
        Check if the identifier (IP or User ID) has exceeded the rate limit.
        Returns True if rate limited (blocked), False otherwise.
        """
        if self._redis and time.monotonic() >= _redis_unhealthy_until:
            try:
                now = time.time()
                window_start = now - self.window_seconds
                key = f"rate:limit:{identifier}"

                async with self._redis.pipeline() as pipe:
                    # 1. Clean up old requests from sliding window
                    pipe.zremrangebyscore(key, 0, window_start)
                    # 2. Count active request timestamps
                    pipe.zcard(key)
                    # 3. Add current timestamp
                    pipe.zadd(key, {str(now): now})
                    # 4. Refresh key TTL
                    pipe.expire(key, max(1, int(self.window_seconds)))
                    results = await pipe.execute()

                _, count, _, _ = results

                # Block when the window is already full (>=), matching the
                # in-memory fallback so both paths allow exactly
                # requests_per_minute + burst requests per window.
                if count >= (self.requests_per_minute + self.burst):
                    return True
                return False
            except Exception as e:
                # Trip the circuit breaker so the outage cannot stall every
                # request: Redis attempts are skipped for the TTL and the
                # in-memory fallback below is used directly.
                _trip_redis_breaker()
                logger.error(f"Redis rate limiting failed, using memory fallback: {e}")

        # Memory Fallback
        now = time.time()
        window_start = now - self.window_seconds
        with self._lock:
            if identifier not in self._memory_db:
                # Sweep stale identifiers BEFORE inserting so the new entry can
                # never be dropped as stale itself, then enforce the cap.
                self._sweep_stale_identifiers(now, window_start)
                self._memory_db[identifier] = []
                self._evict_over_cap()

            # Evict timestamps older than window_seconds
            self._memory_db[identifier] = [
                t for t in self._memory_db[identifier] if t > window_start
            ]

            if len(self._memory_db[identifier]) >= (
                self.requests_per_minute + self.burst
            ):
                return True

            self._memory_db[identifier].append(now)
            return False


_FAILED_LOGIN_STORES: dict[tuple[int, int], dict[str, list[float]]] = {}
_FAILED_LOGIN_PRUNE_AT: dict[tuple[int, int], float] = {}


class LoginAttemptTracker:
    """
    Tracks consecutive failed login attempts per account/IP.
    Allows up to max_attempts failures before locking out for window_seconds (default: 5 attempts per 5 minutes = 300s).
    """

    def __init__(
        self,
        redis_client: async_redis.Redis | None = None,
        max_attempts: int = 5,
        window_seconds: float = 300.0,
    ) -> None:
        self._redis = redis_client
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        config_key = (max_attempts, int(window_seconds))
        self._memory_db = _FAILED_LOGIN_STORES.setdefault(config_key, {})
        self._lock = _MEMORY_STORE_LOCK

    def _sweep_stale_identifiers(self, now: float, window_start: float) -> None:
        config_key = (self.max_attempts, int(self.window_seconds))
        if now < _FAILED_LOGIN_PRUNE_AT.get(config_key, 0.0):
            return
        _FAILED_LOGIN_PRUNE_AT[config_key] = now + _MEMORY_PRUNE_INTERVAL
        stale = [
            ident
            for ident, stamps in self._memory_db.items()
            if not stamps or stamps[-1] <= window_start
        ]
        for ident in stale:
            del self._memory_db[ident]

    def _evict_over_cap(self) -> None:
        while len(self._memory_db) > _MEMORY_MAX_IDENTIFIERS:
            oldest = min(
                self._memory_db,
                key=lambda ident: (
                    self._memory_db[ident][-1]
                    if self._memory_db[ident]
                    else float("inf")
                ),
            )
            del self._memory_db[oldest]

    async def is_locked_out(self, identifier: str) -> bool:
        """Return True if identifier has exceeded allowed failed attempts within window."""
        if self._redis and time.monotonic() >= _redis_unhealthy_until:
            try:
                now = time.time()
                window_start = now - self.window_seconds
                key = f"failed_login:{identifier}"
                async with self._redis.pipeline() as pipe:
                    pipe.zremrangebyscore(key, 0, window_start)
                    pipe.zcard(key)
                    results = await pipe.execute()
                _, count = results
                return count >= self.max_attempts
            except Exception as e:
                _trip_redis_breaker()
                logger.error(
                    f"Redis failed login check failed, using memory fallback: {e}"
                )

        now = time.time()
        window_start = now - self.window_seconds
        with self._lock:
            if identifier not in self._memory_db:
                return False
            self._memory_db[identifier] = [
                t for t in self._memory_db[identifier] if t > window_start
            ]
            return len(self._memory_db[identifier]) >= self.max_attempts

    async def record_failed_attempt(self, identifier: str) -> None:
        """Record a failed login attempt."""
        if self._redis and time.monotonic() >= _redis_unhealthy_until:
            try:
                now = time.time()
                key = f"failed_login:{identifier}"
                async with self._redis.pipeline() as pipe:
                    pipe.zadd(key, {str(now): now})
                    pipe.expire(key, max(1, int(self.window_seconds)))
                    await pipe.execute()
                return
            except Exception as e:
                _trip_redis_breaker()
                logger.error(
                    f"Redis record failed login failed, using memory fallback: {e}"
                )

        now = time.time()
        window_start = now - self.window_seconds
        with self._lock:
            if identifier not in self._memory_db:
                self._sweep_stale_identifiers(now, window_start)
                self._memory_db[identifier] = []
                self._evict_over_cap()
            self._memory_db[identifier] = [
                t for t in self._memory_db[identifier] if t > window_start
            ]
            self._memory_db[identifier].append(now)

    async def reset(self, identifier: str) -> None:
        """Reset failed attempt counters upon successful authentication."""
        if self._redis and time.monotonic() >= _redis_unhealthy_until:
            try:
                key = f"failed_login:{identifier}"
                await self._redis.delete(key)
            except Exception:
                pass

        with self._lock:
            self._memory_db.pop(identifier, None)
