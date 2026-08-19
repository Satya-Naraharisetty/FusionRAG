from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.documents.domain.models import (
    Chunk,
    Document,
    DocumentStatus,
)
from app.documents.infrastructure.embedding_generator import GeminiEmbeddingGenerator
from app.documents.services.embedding_service import EmbeddingService

# --- Low-Level GeminiEmbeddingGenerator Unit Tests ---


@pytest.mark.asyncio
async def test_gemini_embedding_generator_success():
    generator = GeminiEmbeddingGenerator(
        api_key="mock-gemini-key",
        model="text-embedding-004",
        dimension=768,
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "embeddings": [
            {"values": [0.1] * 768},
            {"values": [0.2] * 768},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        embeddings = await generator.batch_generate(["First query", "Second query"])

        assert len(embeddings) == 2
        assert len(embeddings[0]) == 768
        assert len(embeddings[1]) == 768
        assert embeddings[0][0] == 0.1
        assert embeddings[1][0] == 0.2

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "models/text-embedding-004:batchEmbedContents" in args[0]
        assert "key=mock-gemini-key" in args[0]


@pytest.mark.asyncio
async def test_gemini_embedding_generator_dimension_mismatch():
    generator = GeminiEmbeddingGenerator(
        api_key="mock-gemini-key",
        model="text-embedding-004",
        dimension=768,
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "embeddings": [
            {"values": [0.1] * 384},  # Wrong dimension (384 instead of 768)
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            await generator.generate("Test query")


@pytest.mark.asyncio
async def test_gemini_embedding_generator_empty_input():
    generator = GeminiEmbeddingGenerator(
        api_key="mock-gemini-key",
        model="text-embedding-004",
        dimension=768,
    )

    embeddings = await generator.batch_generate([])
    assert embeddings == []


@pytest.mark.asyncio
async def test_gemini_embedding_retry_on_rate_limit():
    """
    Tests that GeminiEmbeddingGenerator retries with exponential backoff on HTTP 429 rate limits.
    """
    generator = GeminiEmbeddingGenerator(
        api_key="mock-key",
        model="text-embedding-004",
        dimension=768,
    )

    import httpx

    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Rate limit", request=MagicMock(), response=mock_429
    )

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {"embeddings": [{"values": [0.05] * 768}]}
    mock_200.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [
            httpx.HTTPStatusError("Rate limit", request=MagicMock(), response=mock_429),
            mock_200,
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            res = await generator.generate("Test text with backoff")

            assert len(res) == 768
            assert mock_post.call_count == 2
            mock_sleep.assert_called_once_with(1.0)


# --- Service Orchestration Tests ---


class MockUnitOfWork:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_gemini_embedding_service_integration(mocker):
    """
    Tests EmbeddingService orchestration with Gemini 768-dim embeddings.
    """
    generator = GeminiEmbeddingGenerator(
        api_key="mock-key",
        model="text-embedding-004",
        dimension=768,
    )
    mocker.patch.object(
        generator,
        "batch_generate",
        new=AsyncMock(return_value=[[0.1] * 768, [0.2] * 768]),
    )

    vector_store = mocker.AsyncMock()
    embedding_repo = mocker.AsyncMock()
    embedding_repo.list_by_document.return_value = []
    embedding_repo.get_by_chunk.return_value = None
    embedding_repo.get_by_chunk_ids.return_value = []

    chunk_repo = mocker.AsyncMock()
    doc_id = uuid4()
    chunks = [
        Chunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="Gemini chunk 1",
            character_start=0,
            character_end=14,
            token_estimate=3,
            created_at=datetime.now(UTC),
        ),
        Chunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=1,
            text="Gemini chunk 2",
            character_start=15,
            character_end=29,
            token_estimate=3,
            created_at=datetime.now(UTC),
        ),
    ]
    chunk_repo.list_by_document.return_value = chunks

    document_repo = mocker.AsyncMock()
    document = Document(
        id=doc_id,
        user_id=uuid4(),
        filename="gemini_test.txt",
        original_filename="gemini_test.txt",
        content_type="text/plain",
        file_size=100,
        checksum="hash",
        status=DocumentStatus.COMPLETED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    document_repo.get_by_id.return_value = document

    uow = MockUnitOfWork()
    time_provider = mocker.MagicMock()
    time_provider.get_now.return_value = datetime.now(UTC)
    uuid_generator = mocker.MagicMock()
    uuid_generator.generate.side_effect = lambda: uuid4()

    service = EmbeddingService(
        embedding_generator=generator,
        vector_store=vector_store,
        embedding_repo=embedding_repo,
        chunk_repo=chunk_repo,
        document_repo=document_repo,
        uow=uow,
        time_provider=time_provider,
        uuid_generator=uuid_generator,
        batch_size=2,
        provider_name="gemini",
        model_name="text-embedding-004",
        dimension=768,
        embedding_version="v1",
    )

    await service.generate_embeddings(doc_id)

    assert generator.batch_generate.call_count == 1
    assert vector_store.upsert.call_count == 1
    assert embedding_repo.save.call_count == 4
