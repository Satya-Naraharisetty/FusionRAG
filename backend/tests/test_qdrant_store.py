from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.documents.infrastructure.persistence.vector_store import QdrantVectorStore


@pytest.mark.asyncio
async def test_qdrant_vector_store_upsert():
    mock_client = AsyncMock()
    mock_client.get_collection.return_value = MagicMock()

    store = QdrantVectorStore(mock_client, "test_collection", 1536)

    vector_ids = [uuid4(), uuid4()]
    vectors = [[0.1] * 1536, [0.2] * 1536]
    payloads = [{"doc": "1"}, {"doc": "2"}]

    await store.upsert(vectors, payloads, vector_ids)

    mock_client.upsert.assert_called_once()
    _, kwargs = mock_client.upsert.call_args
    assert kwargs["collection_name"] == "test_collection"
    points = kwargs["points"]
    assert len(points) == 2
    assert points[0].id == str(vector_ids[0])
    assert points[0].vector == vectors[0]
    assert points[0].payload == payloads[0]


@pytest.mark.asyncio
async def test_qdrant_vector_store_delete():
    mock_client = AsyncMock()
    mock_client.get_collection.return_value = MagicMock()

    store = QdrantVectorStore(mock_client, "test_collection", 1536)

    vector_ids = [uuid4(), uuid4()]
    await store.delete(vector_ids)

    mock_client.delete.assert_called_once()
    _, kwargs = mock_client.delete.call_args
    assert kwargs["collection_name"] == "test_collection"
    assert kwargs["points_selector"].points == [str(vid) for vid in vector_ids]


@pytest.mark.asyncio
async def test_qdrant_vector_store_delete_document():
    mock_client = AsyncMock()
    mock_client.get_collection.return_value = MagicMock()

    store = QdrantVectorStore(mock_client, "test_collection", 1536)

    doc_id = uuid4()
    await store.delete_document(doc_id)

    mock_client.delete.assert_called_once()
    _, kwargs = mock_client.delete.call_args
    assert kwargs["collection_name"] == "test_collection"
    filter_cond = kwargs["points_selector"].must[0]
    assert filter_cond.key == "document_id"
    assert filter_cond.match.value == str(doc_id)


@pytest.mark.asyncio
async def test_qdrant_vector_store_health_success():
    mock_client = AsyncMock()

    mock_collection_info = MagicMock()
    mock_collection_info.config.params.vectors.size = 1536
    mock_client.get_collection.return_value = mock_collection_info

    store = QdrantVectorStore(mock_client, "test_collection", 1536)
    assert await store.health() is True


@pytest.mark.asyncio
async def test_qdrant_vector_store_health_dimension_mismatch():
    mock_client = AsyncMock()

    mock_collection_info = MagicMock()
    mock_collection_info.config.params.vectors.size = 512
    mock_client.get_collection.return_value = mock_collection_info

    store = QdrantVectorStore(mock_client, "test_collection", 1536)
    assert await store.health() is False
