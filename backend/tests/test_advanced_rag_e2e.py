import datetime
import uuid
from unittest.mock import AsyncMock

import pytest

from app.chat.services.token_estimator import CharacterTokenEstimator
from app.documents.domain.models import (
    Chunk,
    DocumentRetrievalScope,
    RetrievedChunk,
    SearchResult,
)
from app.documents.services.context_selector import ContextSelector, SelectedContext
from app.documents.services.fusion import WeightedReciprocalRankFusionEngine
from app.documents.services.mmr import DefaultMMRSelector
from app.documents.services.query_classifier import (
    DeterministicQueryClassifier,
)
from app.documents.services.query_decomposer import DeterministicQueryDecomposer
from app.documents.services.query_expansion import LexicalQueryExpander
from app.documents.services.query_processor import DefaultQueryProcessor
from app.documents.services.reranker import IdentityReranker
from app.documents.services.retrieval_service import RetrievalService


@pytest.mark.asyncio
async def test_advanced_rag_end_to_end_pipeline():
    """
    End-to-End integration test for Advanced RAG pipeline:
    Query -> Query Classification -> Query Expansion & Decomposition ->
    Concurrent Dense + Sparse Retrieval -> Weighted RRF -> Canonical Deduplication ->
    MMR -> Cross-Encoder -> Neighbor Expansion -> Context Selection & Budgeting.
    """
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id_0 = uuid.uuid4()
    chunk_id_1 = uuid.uuid4()
    chunk_id_2 = uuid.uuid4()

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.get_allowed_document_ids.return_value = [doc_id]
    mock_chunk_repo.get_chunks_metadata_stats.return_value = {"count": 10}

    # Adjacent chunk in database for neighbor expansion
    neighbor_db_chunk = Chunk(
        id=chunk_id_2,
        document_id=doc_id,
        chunk_index=2,
        text="Section 3: Incident Response Procedures and SEV-1 escalation.",
        character_start=200,
        character_end=300,
        token_estimate=25,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    mock_chunk_repo.list_by_document.return_value = [neighbor_db_chunk]
    mock_chunk_repo.get_chunks_by_document.return_value = [neighbor_db_chunk]

    c0 = RetrievedChunk(
        chunk_id=chunk_id_0,
        document_id=doc_id,
        document_name="engineering_policies.md",
        text="Section 1: Service Level Agreements and SLO targets.",
        similarity_score=0.92,
        normalized_score=0.92,
        rerank_score=0.95,
        chunk_index=0,
    )
    c1 = RetrievedChunk(
        chunk_id=chunk_id_1,
        document_id=doc_id,
        document_name="engineering_policies.md",
        text="Section 2: Incident Severity Levels SEV-1 and SEV-2.",
        similarity_score=0.88,
        normalized_score=0.88,
        rerank_score=0.91,
        chunk_index=1,
    )

    mock_dense = AsyncMock()
    mock_dense.retrieve.return_value = [c0]
    mock_sparse = AsyncMock()
    mock_sparse.retrieve.return_value = [c1]

    retrieval_service = RetrievalService(
        query_processor=DefaultQueryProcessor(),
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        fusion_engine=WeightedReciprocalRankFusionEngine(rrf_k=60),
        mmr_selector=DefaultMMRSelector(),
        reranker=IdentityReranker(),
        chunk_repo=mock_chunk_repo,
        query_classifier=DeterministicQueryClassifier(),
        query_expander=LexicalQueryExpander(),
        query_decomposer=DeterministicQueryDecomposer(),
        enable_hybrid_search=True,
        enable_mmr=True,
        enable_reranker=True,
        enable_query_expansion=True,
        enable_query_decomposition=True,
        enable_weighted_rrf=True,
    )

    scope = DocumentRetrievalScope(
        user_id=user_id,
        include_library_documents=True,
        include_conversation_documents=True,
    )

    # 1. Execute Retrieval
    search_res: SearchResult = await retrieval_service.retrieve(
        query="What are the SLA targets and also the incident severity classifications?",
        user_id=user_id,
        top_k=5,
        retrieval_scope=scope,
    )

    assert search_res.query_type in ("MULTI_HOP", "COMPARISON", "FACTUAL")
    assert search_res.total_matches > 0
    assert search_res.diagnostics is not None
    assert "total_queries_executed" in search_res.diagnostics

    # 2. Execute Context Selection with Neighbor Expansion
    context_selector = ContextSelector(
        token_estimator=CharacterTokenEstimator(),
        max_context_tokens=4000,
        max_chunks=10,
        min_chunk_score=0.0,
        score_source="rerank_score",
        enable_neighbor_chunks=True,
        neighbor_window=1,
        chunk_repo=mock_chunk_repo,
    )

    selected: SelectedContext = await context_selector.select_context(
        search_res.retrieved_chunks,
        allowed_doc_ids={doc_id},
    )

    assert selected.final_chunk_count >= len(search_res.retrieved_chunks)
    assert len(selected.concatenated_context) > 0
    assert "[Chunk 1]" in selected.concatenated_context
    assert selected.token_count > 0


@pytest.mark.asyncio
async def test_telemetry_does_not_leak_document_content():
    """
    SECURITY TEST:
    Verifies that structured diagnostics and logs contain metrics and queries,
    but never leak sensitive raw document contents or private user credentials.
    """
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.get_allowed_document_ids.return_value = [doc_id]

    c = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        document_name="secret_finance.md",
        text="TOP SECRET FINANCIAL SALARY AND PROFIT NUMBERS",
        similarity_score=0.9,
        chunk_index=0,
    )

    mock_dense = AsyncMock()
    mock_dense.retrieve.return_value = [c]
    mock_sparse = AsyncMock()
    mock_sparse.retrieve.return_value = []

    retrieval_service = RetrievalService(
        query_processor=DefaultQueryProcessor(),
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        chunk_repo=mock_chunk_repo,
        enable_hybrid_search=True,
        enable_query_expansion=True,
    )

    scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)
    res = await retrieval_service.retrieve(
        query="financial summary",
        user_id=user_id,
        top_k=5,
        retrieval_scope=scope,
    )

    diag = res.diagnostics or {}
    diag_str = str(diag)
    # The sensitive text must NOT appear in diagnostics
    assert "TOP SECRET FINANCIAL SALARY" not in diag_str
