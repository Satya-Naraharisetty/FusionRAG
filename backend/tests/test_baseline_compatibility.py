import uuid
from unittest.mock import AsyncMock

import pytest

from app.documents.domain.models import (
    DocumentRetrievalScope,
    RetrievedChunk,
    SearchResult,
)
from app.documents.services.fusion import ReciprocalRankFusionEngine
from app.documents.services.mmr import DefaultMMRSelector
from app.documents.services.query_processor import DefaultQueryProcessor
from app.documents.services.reranker import IdentityReranker
from app.documents.services.retrieval_service import RetrievalService


@pytest.mark.asyncio
async def test_disabled_advanced_path_preserves_exact_phase_2_3_behavior():
    """
    CRITICAL BASELINE COMPATIBILITY TEST:
    Verifies that when advanced RAG features (query expansion, query decomposition,
    weighted RRF) are disabled, the RetrievalService executes the exact Phase 2.3 baseline
    pipeline, returning identical candidate chunk IDs, ordering, scores, citations,
    and retrieval parameters.
    """
    user_id = uuid.uuid4()
    doc_id_1 = uuid.uuid4()
    doc_id_2 = uuid.uuid4()
    chunk_id_1 = uuid.uuid4()
    chunk_id_2 = uuid.uuid4()
    chunk_id_3 = uuid.uuid4()

    # 1. Setup mock repository and retrievers
    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.get_allowed_document_ids.return_value = [doc_id_1, doc_id_2]
    mock_chunk_repo.get_chunks_metadata_stats.return_value = {"count": 10}

    chunk1 = RetrievedChunk(
        chunk_id=chunk_id_1,
        document_id=doc_id_1,
        document_name="engineering_policies.md",
        text="SLO for enterprise tier tenants is 99.99% availability.",
        similarity_score=0.92,
        normalized_score=0.92,
        metadata={"section": "Section 1"},
        chunk_index=0,
    )
    chunk2 = RetrievedChunk(
        chunk_id=chunk_id_2,
        document_id=doc_id_1,
        document_name="engineering_policies.md",
        text="SLO for standard tier tenants is 99.95% availability.",
        similarity_score=0.85,
        normalized_score=0.85,
        metadata={"section": "Section 1"},
        chunk_index=1,
    )
    chunk3 = RetrievedChunk(
        chunk_id=chunk_id_3,
        document_id=doc_id_2,
        document_name="cloud_architecture.md",
        text="Aurora database clusters maintain high availability across AZs.",
        similarity_score=0.78,
        normalized_score=0.78,
        metadata={"section": "Section 2"},
        chunk_index=0,
    )

    mock_dense = AsyncMock()
    mock_dense.retrieve.return_value = [chunk1, chunk2]

    mock_sparse = AsyncMock()
    mock_sparse.retrieve.return_value = [chunk2, chunk3]

    # Explicit baseline configuration with all advanced features disabled
    service = RetrievalService(
        query_processor=DefaultQueryProcessor(),
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        fusion_engine=ReciprocalRankFusionEngine(rrf_k=60),
        mmr_selector=DefaultMMRSelector(),
        reranker=IdentityReranker(),
        chunk_repo=mock_chunk_repo,
        enable_hybrid_search=True,
        enable_mmr=True,
        enable_reranker=True,
        enable_query_expansion=False,
        enable_query_decomposition=False,
        enable_weighted_rrf=False,
        vector_top_k=20,
        bm25_top_k=20,
        rerank_top_k=5,
    )

    query = "enterprise availability SLO"
    scope = DocumentRetrievalScope(
        user_id=user_id,
        include_library_documents=True,
        include_conversation_documents=True,
    )

    result: SearchResult = await service.retrieve(
        query=query,
        user_id=user_id,
        top_k=5,
        retrieval_scope=scope,
    )

    # Verifications
    # 1. Query was processed once via standard baseline processor
    mock_dense.retrieve.assert_called_once()
    mock_sparse.retrieve.assert_called_once()

    # 2. Results match standard RRF + MMR diversity selection
    assert len(result.retrieved_chunks) == 3
    # chunk2 is in both dense (rank 2) and sparse (rank 1) -> highest RRF score (selected 1st)
    # chunk3 provides maximum diversity against chunk2 (selected 2nd by MMR)
    # chunk1 is selected 3rd
    assert result.retrieved_chunks[0].chunk_id == chunk_id_2
    assert result.retrieved_chunks[1].chunk_id == chunk_id_3
    assert result.retrieved_chunks[2].chunk_id == chunk_id_1

    # 3. Verify observable properties
    assert result.original_query == query
    assert result.retrieval_strategy.value == "hybrid"
    assert result.fusion_method.value == "RRF"
    assert result.reranker.value == "IdentityReranker"
    assert result.total_matches == len(result.retrieved_chunks)

    # 4. Citations & chunk metadata intact
    for c in result.retrieved_chunks:
        assert c.document_name in ("engineering_policies.md", "cloud_architecture.md")
        assert c.chunk_id in (chunk_id_1, chunk_id_2, chunk_id_3)

    # 5. Full Observable Context Construction Verification
    from app.chat.services.context_builder import ContextBuilder
    from app.chat.services.token_estimator import CharacterTokenEstimator

    context_builder = ContextBuilder(
        token_estimator=CharacterTokenEstimator(),
        context_selector=None,  # Baseline: no context selector
        max_context_tokens=4000,
    )
    grounded = context_builder.build_context(result.retrieved_chunks)
    context_str = grounded.concatenated_context
    cited_chunks = grounded.chunk_references

    assert "[Chunk 1]" in context_str
    assert "[Chunk 2]" in context_str
    assert "[Chunk 3]" in context_str
    assert len(cited_chunks) == 3
    assert cited_chunks[0].chunk_id == chunk_id_2
    assert cited_chunks[1].chunk_id == chunk_id_3
    assert cited_chunks[2].chunk_id == chunk_id_1
