from unittest.mock import MagicMock

from fastapi import status


def test_liveness_check(client):
    """
    Asserts GET /api/v1/health/liveness returns HTTP 200 and 'alive' status.
    """
    response = client.get("/api/v1/health/liveness")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "alive"}

def test_readiness_check_all_healthy(client):
    """
    Asserts GET /api/v1/health/readiness returns healthy indicators.
    """
    mock_db = MagicMock()
    # Mock the session factory stored in app state to return our mock db session
    client.app.state.db_session_factory = MagicMock(return_value=mock_db)
    client.app.state.redis.ping.return_value = True
    client.app.state.qdrant.get_collections.return_value = MagicMock()

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == status.HTTP_200_OK
    
    data = response.json()
    assert data["status"] == "healthy"
    assert data["services"]["postgres"] == "connected"
    assert data["services"]["redis"] == "connected"
    assert data["services"]["vector_db"] == "connected"
    assert "x-request-id" in response.headers

def test_readiness_check_postgres_down(client):
    """
    Asserts health readiness probe fails if PostgreSQL connection throws an exception.
    """
    mock_db = MagicMock()
    # Simulate Postgres failure on query execution rather than session creation
    mock_db.execute.side_effect = Exception("PostgreSQL connection timed out")
    client.app.state.db_session_factory = MagicMock(return_value=mock_db)
    client.app.state.redis.ping.return_value = True
    client.app.state.qdrant.get_collections.return_value = MagicMock()

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    
    data = response.json()
    assert data["status"] == "unhealthy"
    assert "disconnected" in data["services"]["postgres"]
    assert data["services"]["redis"] == "connected"
    assert data["services"]["vector_db"] == "connected"

def test_readiness_check_redis_down(client):
    """
    Asserts health readiness probe fails if Redis ping returns False.
    """
    mock_db = MagicMock()
    client.app.state.db_session_factory = MagicMock(return_value=mock_db)
    client.app.state.redis.ping.return_value = False
    client.app.state.qdrant.get_collections.return_value = MagicMock()

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["services"]["postgres"] == "connected"
    assert "disconnected" in data["services"]["redis"]
    assert data["services"]["vector_db"] == "connected"
