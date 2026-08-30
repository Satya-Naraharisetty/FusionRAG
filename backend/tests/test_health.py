from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status


@pytest.mark.asyncio
async def test_root_route(client):
    """Asserts root route returns service information."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert "NexusRAG" in response.json()["message"]


@pytest.mark.asyncio
async def test_backend_robots_txt(client):
    """Asserts GET /robots.txt returns crawler policy."""
    response = client.get("/robots.txt")
    assert response.status_code == status.HTTP_200_OK
    assert "User-agent: *" in response.text
    assert "Allow: /docs" in response.text


@pytest.mark.asyncio
async def test_liveness_check(client):
    """
    Asserts GET /api/v1/health/liveness returns HTTP 200 and 'alive' status.
    """
    response = client.get("/api/v1/health/liveness")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_readiness_check_all_healthy(client):
    """
    Asserts GET /api/v1/health/readiness returns healthy indicators.
    """
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()
    mock_db.execute = AsyncMock()

    # Mock the session factory stored in app state to return our mock db session
    client.app.state.db_session_factory = MagicMock(return_value=mock_db)

    # Redis ping mock (async)
    client.app.state.redis.ping = AsyncMock(return_value=True)

    # Qdrant get_collections mock (async)
    client.app.state.qdrant.get_collections = AsyncMock()

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "healthy"
    assert data["services"]["postgres"] == "connected"
    assert data["services"]["redis"] == "connected"
    assert data["services"]["vector_db"] == "connected"
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_readiness_check_postgres_down(client):
    """
    Asserts health readiness probe fails if PostgreSQL connection throws an exception.
    """
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()
    # Simulate Postgres failure on query execution rather than session creation
    mock_db.execute = AsyncMock(
        side_effect=Exception("PostgreSQL connection timed out")
    )
    client.app.state.db_session_factory = MagicMock(return_value=mock_db)
    client.app.state.redis.ping = AsyncMock(return_value=True)
    client.app.state.qdrant.get_collections = AsyncMock()

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    data = response.json()
    assert data["status"] == "unhealthy"
    assert "disconnected" in data["services"]["postgres"]
    assert data["services"]["redis"] == "connected"
    assert data["services"]["vector_db"] == "connected"


@pytest.mark.asyncio
async def test_readiness_check_redis_down(client):
    """
    Asserts health readiness probe fails if Redis ping returns False.
    """
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()
    mock_db.execute = AsyncMock()
    client.app.state.db_session_factory = MagicMock(return_value=mock_db)
    client.app.state.redis.ping = AsyncMock(return_value=False)
    client.app.state.qdrant.get_collections = AsyncMock()

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["services"]["postgres"] == "connected"
    assert "disconnected" in data["services"]["redis"]
    assert data["services"]["vector_db"] == "connected"
