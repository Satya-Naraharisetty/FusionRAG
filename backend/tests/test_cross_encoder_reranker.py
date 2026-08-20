import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.documents.domain.interfaces import Reranker
from app.documents.domain.models import (
    RerankerName,
    RetrievalMode,
    RetrievedChunk,
)
from app.documents.services.reranker import CrossEncoderReranker, IdentityReranker
from app.documents.services.retrieval_service import RetrievalService

# --- 1. Initialization & Model Lifecycle Tests ---


@pytest.mark.asyncio
async def test_cross_encoder_initialization_defaults():
    reranker = CrossEncoderReranker(
        model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
        device="cpu",
        batch_size=16,
        max_length=512,
        concurrency_limit=4,
    )
    assert isinstance(reranker, Reranker)
    assert reranker._model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert reranker._device == "cpu"
    assert reranker._batch_size == 16
    assert reranker._max_length == 512
    assert reranker._concurrency_limit == 4
    # Construction is cheap: model is not loaded yet
    assert reranker._model is None
    assert reranker._init_failed is False


@pytest.mark.asyncio
async def test_cross_encoder_model_loaded_once():
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()

    with patch(
        "sentence_transformers.CrossEncoder", return_value=mock_model
    ) as mock_ce:
        # First call loads model
        reranker.ensure_model_loaded()
        assert reranker._model is mock_model
        assert mock_ce.call_count == 1

        # Second call reuses existing model instance
        reranker.ensure_model_loaded()
        assert mock_ce.call_count == 1


@pytest.mark.asyncio
async def test_cross_encoder_initialization_failure_guard():
    reranker = CrossEncoderReranker(model_name="nonexistent/invalid-model")

    with patch(
        "sentence_transformers.CrossEncoder", side_effect=RuntimeError("Download error")
    ) as mock_ce:
        # First call fails and records failure
        with pytest.raises(RuntimeError, match="Download error"):
            reranker.ensure_model_loaded()

        assert reranker._init_failed is True
        assert reranker._model is None
        assert mock_ce.call_count == 1

        # Subsequent call does not repeatedly retry expensive model load
        with pytest.raises(RuntimeError, match="previously failed"):
            reranker.ensure_model_loaded()

        assert mock_ce.call_count == 1


# --- 2. Candidate Sizing & Scoring Tests ---


@pytest.mark.asyncio
async def test_rerank_empty_candidate_list():
    reranker = CrossEncoderReranker()
    # 0 candidates returns empty list immediately without touching the model
    result = await reranker.rerank("test query", [])
    assert result == []


@pytest.mark.asyncio
async def test_rerank_single_candidate_receives_score():
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict.return_value = [2.45]

    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_name="single.txt",
        text="Unique passage text",
        similarity_score=0.82,
        normalized_score=0.82,
        chunk_index=0,
    )

    with patch("sentence_transformers.CrossEncoder", return_value=mock_model):
        reranked = await reranker.rerank("test query", [chunk])

    assert len(reranked) == 1
    assert reranked[0].chunk_id == chunk.chunk_id
    assert reranked[0].text == "Unique passage text"
    assert reranked[0].similarity_score == 0.82
    assert reranked[0].rerank_score == 2.45


@pytest.mark.asyncio
async def test_rerank_multiple_candidates_reordered_by_score():
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()

    doc_id = uuid4()
    # Initial order from MMR: c1, c2, c3
    c1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="General machine learning overview",
        similarity_score=0.95,
        normalized_score=0.95,
        chunk_index=0,
    )
    c2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="Exact answer to the user query about RAG architectures",
        similarity_score=0.75,
        normalized_score=0.75,
        chunk_index=1,
    )
    c3 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="Marginally related deep learning details",
        similarity_score=0.88,
        normalized_score=0.88,
        chunk_index=2,
    )

    # CrossEncoder scores: c2 is highest (5.2), c1 is medium (1.8), c3 is lowest (-0.4)
    mock_model.predict.return_value = [1.8, 5.2, -0.4]

    with patch("sentence_transformers.CrossEncoder", return_value=mock_model):
        reranked = await reranker.rerank("what is RAG architecture?", [c1, c2, c3])

    # Verified: candidates are reordered strictly by descending rerank_score
    assert len(reranked) == 3
    assert reranked[0].chunk_id == c2.chunk_id
    assert reranked[0].rerank_score == 5.2
    assert reranked[1].chunk_id == c1.chunk_id
    assert reranked[1].rerank_score == 1.8
    assert reranked[2].chunk_id == c3.chunk_id
    assert reranked[2].rerank_score == -0.4

    # Raw scores are preserved without arbitrary sigmoid scaling
    mock_model.predict.assert_called_once_with(
        [
            ("what is RAG architecture?", "General machine learning overview"),
            (
                "what is RAG architecture?",
                "Exact answer to the user query about RAG architectures",
            ),
            ("what is RAG architecture?", "Marginally related deep learning details"),
        ],
        batch_size=16,
        show_progress_bar=False,
    )


# --- 3. Metadata, Scope, and Citation Preservation Tests ---


@pytest.mark.asyncio
async def test_metadata_and_citations_preserved():
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict.return_value = [3.1]

    doc_id = uuid4()
    chunk_id = uuid4()
    original_metadata = {
        "source": "manual.pdf",
        "page": 12,
        "author": "Alice",
        "tags": ["core", "v1"],
    }

    chunk = RetrievedChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        document_name="manual.pdf",
        text="Sample knowledge chunk",
        similarity_score=0.89,
        normalized_score=0.91,
        metadata=original_metadata,
        chunk_index=3,
    )

    with patch("sentence_transformers.CrossEncoder", return_value=mock_model):
        reranked = await reranker.rerank("manual search", [chunk])

    assert len(reranked) == 1
    res = reranked[0]
    assert res.chunk_id == chunk_id
    assert res.document_id == doc_id
    assert res.document_name == "manual.pdf"
    assert res.chunk_index == 3
    assert res.similarity_score == 0.89
    assert res.normalized_score == 0.91
    assert res.rerank_score == 3.1
    assert res.metadata == original_metadata


# --- 4. Async Safety & Concurrency Tests ---


@pytest.mark.asyncio
async def test_async_concurrency_limiting():
    concurrency_limit = 2
    reranker = CrossEncoderReranker(concurrency_limit=concurrency_limit)
    mock_model = MagicMock()

    active_inferences = 0
    max_observed_concurrency = 0

    def slow_predict(pairs, **kwargs):
        nonlocal active_inferences, max_observed_concurrency
        active_inferences += 1
        if active_inferences > max_observed_concurrency:
            max_observed_concurrency = active_inferences
        time.sleep(0.05)
        scores = [1.0] * len(pairs)
        active_inferences -= 1
        return scores

    mock_model.predict.side_effect = slow_predict

    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_name="doc.txt",
        text="Passage",
        similarity_score=0.8,
        chunk_index=0,
    )

    with patch("sentence_transformers.CrossEncoder", return_value=mock_model):
        # Fire 6 concurrent rerank calls
        tasks = [reranker.rerank("query", [chunk]) for _ in range(6)]
        results = await asyncio.gather(*tasks)

    assert len(results) == 6
    # Concurrency never exceeded the configured semaphore limit
    assert max_observed_concurrency <= concurrency_limit


# --- 5. Graceful Fallback & Resilience Tests ---


@pytest.mark.asyncio
async def test_fallback_on_model_initialization_failure():
    reranker = CrossEncoderReranker(model_name="failing-model")
    doc_id = uuid4()
    c1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="A",
        similarity_score=0.9,
        chunk_index=0,
    )
    c2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="B",
        similarity_score=0.8,
        chunk_index=1,
    )

    with patch(
        "sentence_transformers.CrossEncoder",
        side_effect=Exception("CUDA out of memory"),
    ):
        reranked = await reranker.rerank("query", [c1, c2])

    # Gracefully falls back to exact incoming MMR order with no fabricated scores
    assert len(reranked) == 2
    assert reranked[0].chunk_id == c1.chunk_id
    assert reranked[1].chunk_id == c2.chunk_id
    assert reranked[0].rerank_score is None
    assert reranked[1].rerank_score is None


@pytest.mark.asyncio
async def test_fallback_on_inference_runtime_error():
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict.side_effect = RuntimeError("Inference tensor shape mismatch")

    doc_id = uuid4()
    c1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="A",
        similarity_score=0.9,
        chunk_index=0,
    )
    c2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="B",
        similarity_score=0.8,
        chunk_index=1,
    )

    with patch("sentence_transformers.CrossEncoder", return_value=mock_model):
        reranked = await reranker.rerank("query", [c1, c2])

    # Gracefully falls back to incoming MMR candidate order
    assert len(reranked) == 2
    assert reranked[0].chunk_id == c1.chunk_id
    assert reranked[1].chunk_id == c2.chunk_id


# --- 6. RetrievalService Full Integration Tests ---


@pytest.mark.asyncio
async def test_retrieval_service_cross_encoder_integration():
    doc_id = uuid4()
    c1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="Less relevant chunk with high BM25 keyword overlap",
        similarity_score=0.95,
        chunk_index=0,
    )
    c2 = RetrievedChunk(
        chunk_id=uuid4(),
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

    # CrossEncoder scores: c2 is much more relevant (4.8) than c1 (-1.2)
    mock_model = MagicMock()
    mock_model.predict.return_value = [-1.2, 4.8]

    reranker = CrossEncoderReranker()
    reranker._model = mock_model

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

    user_id = uuid4()
    result = await service.retrieve(
        query="neural search",
        user_id=user_id,
        top_k=2,
        retrieval_mode=RetrievalMode.HYBRID,
    )

    # Cross-encoder reordered candidates: c2 is now top match despite lower dense/BM25 score
    assert len(result.retrieved_chunks) == 2
    assert result.retrieved_chunks[0].chunk_id == c2.chunk_id
    assert result.retrieved_chunks[0].rerank_score == 4.8
    assert result.retrieved_chunks[1].chunk_id == c1.chunk_id
    assert result.retrieved_chunks[1].rerank_score == -1.2
    assert result.reranker == RerankerName.CROSS_ENCODER


# --- 7. Real CrossEncoder Execution Benchmark & Verification Test ---


@pytest.mark.asyncio
async def test_real_cross_encoder_live_execution_and_benchmark():
    """
    Live deterministic verification test:
    Loads the real ms-marco-MiniLM-L-6-v2 cross-encoder model,
    reranks real text passages against a query, verifies semantic reordering,
    and measures CPU reranking latency.
    """
    reranker = CrossEncoderReranker(
        model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
        device="cpu",
        batch_size=8,
    )

    # 1. Ensure real model loads cleanly
    t0_load = time.perf_counter()
    reranker.ensure_model_loaded()
    load_time_ms = (time.perf_counter() - t0_load) * 1000
    assert reranker._model is not None

    query = "What is the capital of France?"
    doc_id = uuid4()

    # Passages in incoming order:
    # 0: Irrelevant passage about Python programming
    # 1: Distractor passage about Berlin, Germany
    # 2: Direct answer passage about Paris, France
    p0 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="france.txt",
        text="Python is a popular general-purpose programming language.",
        similarity_score=0.90,
        chunk_index=0,
    )
    p1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="france.txt",
        text="Berlin is the capital and largest city of Germany by both area and population.",
        similarity_score=0.88,
        chunk_index=1,
    )
    p2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="france.txt",
        text="Paris is the capital and most populous city of France.",
        similarity_score=0.70,
        chunk_index=2,
    )

    # 2. Execute live cross-encoder rerank and measure latency
    t0_infer = time.perf_counter()
    reranked = await reranker.rerank(query, [p0, p1, p2])
    infer_time_ms = (time.perf_counter() - t0_infer) * 1000

    # 3. Verify real semantic rank permutation
    assert len(reranked) == 3
    # Paris passage MUST be ranked #1
    assert reranked[0].chunk_id == p2.chunk_id
    assert reranked[0].rerank_score is not None

    # Python passage MUST be lowest ranked
    assert reranked[2].chunk_id == p0.chunk_id

    # Verify score ordering: Paris > Berlin > Python
    assert (
        reranked[0].rerank_score > reranked[1].rerank_score > reranked[2].rerank_score
    )

    print(
        f"\n[BENCHMARK] CrossEncoder live verification: "
        f"model_load={load_time_ms:.2f}ms, inference_latency={infer_time_ms:.2f}ms for 3 candidates. "
        f"Top score (Paris)={reranked[0].rerank_score:.4f}, Lowest score (Python)={reranked[2].rerank_score:.4f}"
    )


# --- 8. Dependency Injection & Lifespan Warmup Tests ---


@pytest.mark.asyncio
async def test_di_get_reranker_enabled_and_disabled(monkeypatch):
    import app.api.dependencies as deps
    from app.core.config import settings

    # 1. When ENABLE_RERANKER is False -> IdentityReranker
    monkeypatch.setattr(settings, "ENABLE_RERANKER", False)
    deps._reranker_instance = None
    reranker_disabled = deps.get_reranker()
    assert isinstance(reranker_disabled, IdentityReranker)

    # 2. When ENABLE_RERANKER is True -> CrossEncoderReranker
    monkeypatch.setattr(settings, "ENABLE_RERANKER", True)
    deps._reranker_instance = None
    reranker_enabled = deps.get_reranker()
    assert isinstance(reranker_enabled, CrossEncoderReranker)
    # DI object creation is cheap (model not loaded during get_reranker)
    assert reranker_enabled._model is None


@pytest.mark.asyncio
async def test_lifespan_warmup_failure_does_not_prevent_startup(monkeypatch):
    """
    Startup warmup failure must not prevent application startup;
    the application logs a warning and retrieval degrades safely.
    """
    from fastapi import FastAPI

    from app.core.config import settings
    from app.main import lifespan

    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "ENABLE_RERANKER", True)

    test_app = FastAPI(lifespan=lifespan)

    # Simulate reranker model warmup raising a network/download error
    mock_reranker = MagicMock()
    mock_reranker.ensure_model_loaded.side_effect = RuntimeError(
        "HuggingFace unreachable"
    )

    with patch("app.api.dependencies.get_reranker", return_value=mock_reranker):
        # Lifespan startup must proceed without raising an unhandled exception
        async with lifespan(test_app):
            assert test_app.state.started_at > 0

    assert mock_reranker.ensure_model_loaded.call_count == 1
