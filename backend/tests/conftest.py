import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

# 1. Set environment variables
os.environ["ENV"] = "testing"
os.environ["POSTGRES_SERVER"] = "mock_db"
os.environ["POSTGRES_USER"] = "mock_user"
os.environ["POSTGRES_PASSWORD"] = "mock_password"
os.environ["POSTGRES_DB"] = "mock_db"
os.environ["REDIS_HOST"] = "mock_redis"
os.environ["QDRANT_HOST"] = "mock_qdrant"
os.environ["GEMINI_API_KEY"] = "mock-gemini-key"
os.environ["JWT_SECRET"] = "mock_secret_key_at_least_32_bytes_long_for_tests!"
os.environ["REQUIRE_EMAIL_VERIFICATION"] = "false"
os.environ["BACKEND_CORS_ORIGINS"] = (
    '["http://localhost:5173","http://127.0.0.1:5173","http://localhost","http://127.0.0.1"]'
)


# 2. Patch database connection helper functions before app.main imports them
import app.db.session  # noqa: E402

app.db.session.init_postgres_engine = MagicMock(
    side_effect=lambda url: (
        create_async_engine(
            url.replace("postgresql://", "postgresql+asyncpg://", 1),
            poolclass=NullPool,
        )
        if ("test" in str(url) or "5433" in str(url))
        else AsyncMock()
    )
)


def _create_mock_redis_client(*args, **kwargs):
    mock_redis = AsyncMock()
    mock_pipe = AsyncMock()
    mock_pipe.__aenter__.return_value = mock_pipe
    mock_pipe.__aexit__.return_value = None
    mock_pipe.execute = AsyncMock(return_value=[None, 0, None, None])
    mock_pipe.zremrangebyscore = MagicMock()
    mock_pipe.zcard = MagicMock()
    mock_pipe.zadd = MagicMock()
    mock_pipe.expire = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipe)
    return mock_redis


def _create_mock_qdrant_client(*args, **kwargs):
    mock_qdrant = AsyncMock()
    mock_qdrant.get_collection = AsyncMock()
    mock_qdrant.create_collection = AsyncMock()
    mock_qdrant.create_payload_index = AsyncMock()
    mock_qdrant.delete = AsyncMock()
    mock_qdrant.upsert = AsyncMock()
    mock_qdrant.search = AsyncMock(return_value=[])
    mock_qdrant.get_collections = AsyncMock(return_value=MagicMock())
    return mock_qdrant


app.db.session.init_redis_client = MagicMock(side_effect=_create_mock_redis_client)
app.db.session.init_qdrant_client = MagicMock(side_effect=_create_mock_qdrant_client)

# 3. Patch application main startup checks
import app.main  # noqa: E402

app.main.verify_postgres_connectivity = AsyncMock()
app.main.verify_alembic_migrations = AsyncMock()
app.main.run_startup_validations = MagicMock()

# 4. Patch the durable cleanup worker so it does not open real asyncpg connections
import app.documents.services.cleanup_worker  # noqa: E402

app.documents.services.cleanup_worker.run_durable_cleanup_recovery = MagicMock()


from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_process_global_state():
    """
    Reset process-level singletons between tests so no test inherits state from
    a previous one, keeping the suite order-independent.
    """
    import app.core.security.rate_limiter as rate_limiter_module

    rate_limiter_module._MEMORY_STORES.clear()
    rate_limiter_module._MEMORY_PRUNE_AT.clear()
    rate_limiter_module._FAILED_LOGIN_STORES.clear()
    rate_limiter_module._FAILED_LOGIN_PRUNE_AT.clear()
    rate_limiter_module._redis_unhealthy_until = 0.0

    import app.api.dependencies as dependencies_module

    dependencies_module._index_cache_instance = None
    dependencies_module._in_memory_task_queue_instance = None
    yield
    app.main.app.dependency_overrides.clear()


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_database_schema():
    """
    Ensure all database tables exist before any tests run, supporting
    arbitrary test execution order against fresh databases (e.g. CI).
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.pool import NullPool

        from app.db.models import Base
        from tests.db import TEST_DATABASE_URL

        sync_engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
        Base.metadata.create_all(bind=sync_engine)
        sync_engine.dispose()
    except Exception:
        # Non-database testing environments
        pass


@pytest.fixture(scope="module")
def client():
    """
    TestClient fixture executing app startup and shutdown lifespan cycles.
    """
    with TestClient(app.main.app) as c:
        yield c
