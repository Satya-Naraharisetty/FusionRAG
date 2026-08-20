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
from app.documents.services.query_classifier import DeterministicQueryClassifier
from app.documents.services.query_decomposer import DeterministicQueryDecomposer
from app.documents.services.query_expansion import LexicalQueryExpander
from app.documents.services.query_processor import DefaultQueryProcessor
from app.documents.services.reranker import IdentityReranker
from app.documents.services.retrieval_service import RetrievalService


@pytest.mark.asyncio
async def test_multi_query_retrieval_merges_results():
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id_1 = uuid.uuid4()
    chunk_id_2 = uuid.uuid4()

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.get_allowed_document_ids.return_value = [doc_id]
    mock_chunk_repo.get_chunks_metadata_stats.return_value = {"count": 5}

    c1 = RetrievedChunk(
        chunk_id=chunk_id_1,
        document_id=doc_id,
        document_name="api_specifications.md",
        text="JWT access token expiry is 15 minutes.",
        similarity_score=0.9,
        normalized_score=0.9,
        chunk_index=0,
    )
    c2 = RetrievedChunk(
        chunk_id=chunk_id_2,
        document_id=doc_id,
        document_name="api_specifications.md",
        text="JSON Web Token lifetime validity details.",
        similarity_score=0.88,
        normalized_score=0.88,
        chunk_index=1,
    )

    mock_dense = AsyncMock()
    mock_dense.retrieve.return_value = [c1]

    mock_sparse = AsyncMock()
    mock_sparse.retrieve.return_value = [c2]

    service = RetrievalService(
        query_processor=DefaultQueryProcessor(),
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        fusion_engine=ReciprocalRankFusionEngine(rrf_k=60),
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
        max_total_retrieval_queries=6,
    )

    scope = DocumentRetrievalScope(
        user_id=user_id,
        include_library_documents=True,
        include_conversation_documents=True,
    )

    res: SearchResult = await service.retrieve(
        query="JWT expiry",
        user_id=user_id,
        top_k=5,
        retrieval_scope=scope,
    )

    assert len(res.retrieved_chunks) > 0
    # Original query is always preserved
    assert res.original_query == "JWT expiry"
    assert res.diagnostics is not None
    assert res.diagnostics["total_queries_executed"] >= 1


@pytest.mark.asyncio
async def test_hard_query_budget_enforcement():
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.get_allowed_document_ids.return_value = [doc_id]

    mock_dense = AsyncMock()
    mock_dense.retrieve.return_value = []
    mock_sparse = AsyncMock()
    mock_sparse.retrieve.return_value = []

    # Configured with hard budget of 2 queries
    service = RetrievalService(
        query_processor=DefaultQueryProcessor(),
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        chunk_repo=mock_chunk_repo,
        enable_hybrid_search=True,
        enable_query_expansion=True,
        max_total_retrieval_queries=2,
    )

    scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)
    res = await service.retrieve(
        query="JWT and OAuth and SLA and RAG and DB",
        user_id=user_id,
        top_k=5,
        retrieval_scope=scope,
    )

    assert res.diagnostics["total_queries_executed"] <= 2
    # Original query must be query 0
    assert (
        res.diagnostics["retrieval_queries"][0]
        == "JWT and OAuth and SLA and RAG and DB"
    )
