import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.documents.domain.models import RetrievedChunk
from app.documents.services.reranker import JinaReranker


def _create_dummy_chunk(
    chunk_id: str, text: str, initial_score: float = 0.5
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name="test_doc.txt",
        text=text,
        similarity_score=initial_score,
        chunk_index=0,
    )


@pytest.mark.asyncio
async def test_jina_reranker_success():
    chunk1 = _create_dummy_chunk("1", "Apples are delicious fruits.")
    chunk2 = _create_dummy_chunk("2", "Quantum computing uses qubits.")
    chunk3 = _create_dummy_chunk("3", "Oranges and apples grow on trees.")

    chunks = [chunk1, chunk2, chunk3]
    query = "What fruits grow on trees?"

    mock_jina_response = {
        "model": "jina-reranker-v2-base-multilingual",
        "results": [
            {"index": 2, "document": {"text": chunk3.text}, "relevance_score": 0.95},
            {"index": 0, "document": {"text": chunk1.text}, "relevance_score": 0.82},
            {"index": 1, "document": {"text": chunk2.text}, "relevance_score": 0.05},
        ],
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_jina_response,
        request=httpx.Request("POST", "https://api.jina.ai/v1/rerank"),
    )

    reranker = JinaReranker(api_key="test_jina_key", max_retries=0)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await reranker.rerank(query, chunks)

    assert len(result) == 3
    # Top result should be chunk3 (index 2)
    assert result[0].text == "Oranges and apples grow on trees."
    assert result[0].rerank_score == 0.95
    # Second result should be chunk1 (index 0)
    assert result[1].text == "Apples are delicious fruits."
    assert result[1].rerank_score == 0.82
    # Third result should be chunk2 (index 1)
    assert result[2].text == "Quantum computing uses qubits."
    assert result[2].rerank_score == 0.05


@pytest.mark.asyncio
async def test_jina_reranker_empty_chunks():
    reranker = JinaReranker(api_key="test_jina_key")
    result = await reranker.rerank("some query", [])
    assert result == []


@pytest.mark.asyncio
async def test_jina_reranker_missing_key_fallback():
    chunk1 = _create_dummy_chunk("1", "Text 1")
    chunk2 = _create_dummy_chunk("2", "Text 2")
    chunks = [chunk1, chunk2]

    reranker = JinaReranker(api_key="")
    result = await reranker.rerank("query", chunks)
    # Should fallback gracefully to original chunk ordering
    assert result == chunks


@pytest.mark.asyncio
async def test_jina_reranker_http_error_fallback():
    chunk1 = _create_dummy_chunk("1", "Text 1")
    chunk2 = _create_dummy_chunk("2", "Text 2")
    chunks = [chunk1, chunk2]

    mock_response = httpx.Response(
        status_code=500,
        text="Internal Server Error",
        request=httpx.Request("POST", "https://api.jina.ai/v1/rerank"),
    )

    reranker = JinaReranker(api_key="test_jina_key", max_retries=0)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await reranker.rerank("query", chunks)

    # Should fallback gracefully without raising
    assert len(result) == 2
    assert result == chunks


@pytest.mark.asyncio
async def test_jina_reranker_timeout_fallback():
    chunk1 = _create_dummy_chunk("1", "Text 1")
    chunks = [chunk1]

    reranker = JinaReranker(api_key="test_jina_key", max_retries=0)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Connection timed out")
        result = await reranker.rerank("query", chunks)

    assert result == chunks


def test_dual_gemini_api_key_resolution():
    # Test case 1: Dedicated keys provided
    settings = Settings(
        GEMINI_FALLBACK_API_KEY="universal_fallback_key",
        GEMINI_EMBEDDING_API_KEY="dedicated_embedding_key",
        GEMINI_LLM_API_KEY="dedicated_llm_key",
    )
    assert settings.get_gemini_embedding_api_key() == "dedicated_embedding_key"
    assert settings.get_gemini_llm_api_key() == "dedicated_llm_key"
    assert settings.get_gemini_fallback_api_key() == "universal_fallback_key"

    # Test case 2: Dedicated keys empty, falls back to GEMINI_FALLBACK_API_KEY
    settings_fallback = Settings(
        GEMINI_FALLBACK_API_KEY="universal_fallback_key",
        GEMINI_EMBEDDING_API_KEY="",
        GEMINI_LLM_API_KEY="",
    )
    assert settings_fallback.get_gemini_embedding_api_key() == "universal_fallback_key"
    assert settings_fallback.get_gemini_llm_api_key() == "universal_fallback_key"

    # Test case 3: Legacy GEMINI_API_KEY still supported
    settings_legacy = Settings(
        GEMINI_API_KEY="legacy_key",
        GEMINI_FALLBACK_API_KEY="",
        GEMINI_EMBEDDING_API_KEY="",
        GEMINI_LLM_API_KEY="",
    )
    assert settings_legacy.get_gemini_embedding_api_key() == "legacy_key"
    assert settings_legacy.get_gemini_llm_api_key() == "legacy_key"


@pytest.mark.asyncio
async def test_di_get_reranker_enabled_and_disabled(monkeypatch):
    import app.api.dependencies as deps
    from app.core.config import settings
    from app.documents.services.reranker import IdentityReranker

    # 1. When ENABLE_RERANKER is False -> IdentityReranker
    monkeypatch.setattr(settings, "ENABLE_RERANKER", False)
    deps._reranker_instance = None
    reranker_disabled = deps.get_reranker()
    assert isinstance(reranker_disabled, IdentityReranker)

    # 2. When ENABLE_RERANKER is True and JINA_API_KEY is configured -> JinaReranker
    monkeypatch.setattr(settings, "ENABLE_RERANKER", True)
    monkeypatch.setattr(settings, "RERANKER_PROVIDER", "jina")
    monkeypatch.setattr(settings, "JINA_API_KEY", "mock-jina-key")
    deps._reranker_instance = None
    jina_reranker = deps.get_reranker()
    assert isinstance(jina_reranker, JinaReranker)


@pytest.mark.asyncio
async def test_retrieval_service_jina_reranker_integration():
    from unittest.mock import MagicMock

    from app.documents.domain.models import RerankerName, RetrievalMode
    from app.documents.services.retrieval_service import RetrievalService

    doc_id = uuid.uuid4()
    c1 = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="Less relevant chunk with high BM25 keyword overlap",
        similarity_score=0.95,
        chunk_index=0,
    )
    c2 = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="Highly relevant semantic answer to the query",
        similarity_score=0.70,
        chunk_index=1,
    )

    processor = MagicMock()
    processor.process.return_value.cleaned_query = "neural search"
    processor.process.return_value.expanded_query = "neural search"

    dense_retriever = MagicMock()
    dense_retriever.retrieve = AsyncMock(return_value=[c1, c2])

    sparse_retriever = MagicMock()
    sparse_retriever.retrieve = AsyncMock(return_value=[c1])

    fusion_engine = MagicMock()
    fusion_engine.fuse.return_value = [c1, c2]

    mmr_selector = MagicMock()
    mmr_selector.select.return_value = [c1, c2]

    reranker = JinaReranker(api_key="test-key", max_retries=0)
    mock_response = httpx.Response(
        status_code=200,
        json={
            "results": [
                {"index": 1, "document": {"text": c2.text}, "relevance_score": 0.99},
                {"index": 0, "document": {"text": c1.text}, "relevance_score": 0.10},
            ]
        },
        request=httpx.Request("POST", "https://api.jina.ai/v1/rerank"),
    )

    chunk_repo = MagicMock()
    chunk_repo.get_allowed_document_ids = AsyncMock(return_value=[doc_id])

    service = RetrievalService(
        query_processor=processor,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        fusion_engine=fusion_engine,
        mmr_selector=mmr_selector,
        reranker=reranker,
        chunk_repo=chunk_repo,
        enable_hybrid_search=True,
        enable_mmr=True,
        enable_reranker=True,
        rerank_top_k=5,
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await service.retrieve(
            query="neural search",
            user_id=uuid.uuid4(),
            top_k=2,
            retrieval_mode=RetrievalMode.HYBRID,
        )

    assert len(result.retrieved_chunks) == 2
    assert result.retrieved_chunks[0].chunk_id == c2.chunk_id
    assert result.retrieved_chunks[0].rerank_score == 0.99
    assert result.retrieved_chunks[1].chunk_id == c1.chunk_id
    assert result.retrieved_chunks[1].rerank_score == 0.10
    assert (
        result.reranker == RerankerName.JINA_CROSS_ENCODER
        or result.reranker == RerankerName.JINA
    )


@pytest.mark.asyncio
async def test_jina_embedding_generator_success():
    from app.documents.infrastructure.embedding_generator import JinaEmbeddingGenerator

    generator = JinaEmbeddingGenerator(
        api_key="mock-key",
        model="jina-embeddings-v3",
        dimension=4,
    )
    assert generator.dimension == 4

    mock_response = httpx.Response(
        status_code=200,
        json={
            "data": [
                {"embedding": [0.1, 0.2, 0.3, 0.4]},
                {"embedding": [0.5, 0.6, 0.7, 0.8]},
            ]
        },
        request=httpx.Request("POST", "https://api.jina.ai/v1/embeddings"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        embeddings = await generator.batch_generate(["doc1", "doc2"])

    assert len(embeddings) == 2
    assert embeddings[0] == [0.1, 0.2, 0.3, 0.4]
    assert embeddings[1] == [0.5, 0.6, 0.7, 0.8]


@pytest.mark.asyncio
async def test_jina_embedding_generator_single_generate():
    from app.documents.infrastructure.embedding_generator import JinaEmbeddingGenerator

    generator = JinaEmbeddingGenerator(
        api_key="mock-key",
        model="jina-embeddings-v3",
        dimension=4,
    )

    mock_response = httpx.Response(
        status_code=200,
        json={"data": [{"embedding": [0.9, 0.8, 0.7, 0.6]}]},
        request=httpx.Request("POST", "https://api.jina.ai/v1/embeddings"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        embedding = await generator.generate("query text")

    assert embedding == [0.9, 0.8, 0.7, 0.6]
    called_payload = mock_post.call_args[1]["json"]
    assert called_payload["task"] == "retrieval.query"
    assert called_payload["dimensions"] == 4


def test_get_embedding_generator_jina_provider(monkeypatch):
    import app.api.dependencies as deps
    from app.documents.infrastructure.embedding_generator import JinaEmbeddingGenerator

    deps._embedding_generator_instance = None
    monkeypatch.setattr(deps.settings, "EMBEDDING_PROVIDER", "jina")
    monkeypatch.setattr(deps.settings, "EMBEDDING_MODEL", "jina-embeddings-v3")
    monkeypatch.setattr(deps.settings, "EMBEDDING_DIMENSION", 768)
    monkeypatch.setattr(deps.settings, "JINA_API_KEY", "test-jina-key")

    gen = deps.get_embedding_generator()
    assert isinstance(gen, JinaEmbeddingGenerator)
    assert gen.dimension == 768
    deps._embedding_generator_instance = None
