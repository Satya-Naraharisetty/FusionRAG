"""
Infrastructure Chaos & Resilience Verification Suite.

Comprehensive tests verifying:
1. Health readiness degradation when PostgreSQL connection fails.
2. Health readiness degradation when Redis cluster is unreachable.
3. Health readiness degradation when Qdrant vector database is down.
4. Dense retriever timeout handling and error bounding.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import status

from app.documents.services.dense_retriever import QdrantDenseRetriever


@pytest.mark.asyncio
async def test_readiness_degrades_when_postgres_unresponsive(client, monkeypatch):
    """
    Chaos Test: Verifies that when PostgreSQL is unresponsive,
    /api/v1/health/readiness returns 503 Service Unavailable with postgres disconnected.
    """
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()
    # Simulate DB connection timeout / connection refused
    mock_db.execute = AsyncMock(
        side_effect=ConnectionRefusedError("PostgreSQL connection refused")
    )

    monkeypatch.setattr(
        client.app.state, "db_session_factory", MagicMock(return_value=mock_db)
    )
    monkeypatch.setattr(client.app.state.redis, "ping", AsyncMock(return_value=True))
    monkeypatch.setattr(client.app.state.qdrant, "get_collections", AsyncMock())

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["services"]["postgres"] == "disconnected"
    assert data["services"]["redis"] == "connected"
    assert data["services"]["vector_db"] == "connected"


@pytest.mark.asyncio
async def test_readiness_degrades_when_redis_unresponsive(client, monkeypatch):
    """
    Chaos Test: Verifies that when Redis is down,
    /api/v1/health/readiness returns 503 Service Unavailable with redis disconnected.
    """
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()
    mock_db.execute = AsyncMock()

    monkeypatch.setattr(
        client.app.state, "db_session_factory", MagicMock(return_value=mock_db)
    )
    # Simulate Redis connection failure
    monkeypatch.setattr(
        client.app.state.redis,
        "ping",
        AsyncMock(side_effect=ConnectionError("Redis connection lost")),
    )
    monkeypatch.setattr(client.app.state.qdrant, "get_collections", AsyncMock())

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["services"]["postgres"] == "connected"
    assert data["services"]["redis"] == "disconnected"


@pytest.mark.asyncio
async def test_readiness_degrades_when_qdrant_unresponsive(client, monkeypatch):
    """
    Chaos Test: Verifies that when Qdrant is down,
    /api/v1/health/readiness returns 503 Service Unavailable with vector_db disconnected.
    """
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()
    mock_db.execute = AsyncMock()

    monkeypatch.setattr(
        client.app.state, "db_session_factory", MagicMock(return_value=mock_db)
    )
    monkeypatch.setattr(client.app.state.redis, "ping", AsyncMock(return_value=True))
    # Simulate Qdrant HTTP/gRPC connection failure
    monkeypatch.setattr(
        client.app.state.qdrant,
        "get_collections",
        AsyncMock(side_effect=Exception("Qdrant connection timeout")),
    )

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["services"]["vector_db"] == "disconnected"


@pytest.mark.asyncio
async def test_dense_retriever_timeout_bounding():
    """
    Chaos Test: Verifies that QdrantDenseRetriever respects search_timeout parameter
    and handles empty search results when vector store search returns None or empty.
    """
    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(return_value=[0.1] * 768)

    mock_vector_store = MagicMock()
    # Simulate vector store returning empty or timing out safely
    mock_vector_store.search = AsyncMock(return_value=[])

    mock_chunk_repo = MagicMock()
    mock_chunk_repo.batch_lookup = AsyncMock(return_value=[])

    retriever = QdrantDenseRetriever(
        embedding_generator=mock_generator,
        vector_store=mock_vector_store,
        chunk_repo=mock_chunk_repo,
        similarity_threshold=0.25,
        search_timeout=1.5,
    )

    results = await retriever.retrieve(
        query="resilience query",
        user_id=uuid4(),
        top_k=5,
    )

    assert results == []
    # Verify timeout parameter was correctly passed down to vector store
    mock_vector_store.search.assert_awaited_once()
    assert mock_vector_store.search.call_args.kwargs.get("timeout") == 1.5
