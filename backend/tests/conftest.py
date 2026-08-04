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


@pytest.fixture(scope="module")
def client():
    """
    TestClient fixture executing app startup and shutdown lifespan cycles.
    """
    with TestClient(app.main.app) as c:
        yield c
