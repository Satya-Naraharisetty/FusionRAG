import os
from unittest.mock import MagicMock

import pytest

# 1. Set environment variables
os.environ["POSTGRES_SERVER"] = "mock_db"
os.environ["POSTGRES_USER"] = "mock_user"
os.environ["POSTGRES_PASSWORD"] = "mock_password"
os.environ["POSTGRES_DB"] = "mock_db"
os.environ["REDIS_HOST"] = "mock_redis"
os.environ["QDRANT_HOST"] = "mock_qdrant"
os.environ["OPENAI_API_KEY"] = "mock-key"
os.environ["JWT_SECRET"] = "mock_secret"


# 2. Patch database connection helper functions before app.main imports them
import app.db.session  # noqa: E402

app.db.session.init_postgres_engine = MagicMock(return_value=MagicMock())
app.db.session.init_redis_client = MagicMock(return_value=MagicMock())
app.db.session.init_qdrant_client = MagicMock(return_value=MagicMock())

# 3. Patch application main startup checks
import app.main  # noqa: E402

app.main.verify_postgres_connectivity = MagicMock()
app.main.run_startup_validations = MagicMock()

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_process_global_state():
    """
    Reset process-level singletons between tests so no test inherits state from
    a previous one, keeping the suite order-independent:

    * The in-memory rate-limit fallback store (and its sweep-deadline
      bookkeeping) plus the Redis health circuit breaker. The store is a
      module-level singleton shared across requests by design (it must survive
      the per-request RateLimiter instances), which makes it process-global.
    * The shared InMemoryIndexCache (user_has_chunks / BM25 cache). It is a
      module-level singleton so the cached "no chunks" determination actually
      survives between requests; clearing it keeps tests isolated.

    The shared embedding generator is NOT reset: it is stateless after
    construction and loading its model is the expensive step we deliberately
    pay only once per process.
    """
    import app.core.security.rate_limiter as rate_limiter_module

    rate_limiter_module._MEMORY_STORES.clear()
    rate_limiter_module._MEMORY_PRUNE_AT.clear()
    rate_limiter_module._redis_unhealthy_until = 0.0

    import app.api.dependencies as dependencies_module

    dependencies_module._index_cache_instance = None
    yield


@pytest.fixture(scope="module")
def client():
    """
    TestClient fixture executing app startup and shutdown lifespan cycles.
    """
    with TestClient(app.main.app) as c:
        yield c
