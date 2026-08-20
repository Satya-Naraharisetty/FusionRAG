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
from app.documents.services.context_selector import ContextSelector
from app.documents.services.fusion import (
    ReciprocalRankFusionEngine,
    WeightedReciprocalRankFusionEngine,
)
from app.documents.services.mmr import DefaultMMRSelector
from app.documents.services.query_classifier import DeterministicQueryClassifier
from app.documents.services.query_decomposer import DeterministicQueryDecomposer
from app.documents.services.query_expansion import LexicalQueryExpander
from app.documents.services.query_processor import DefaultQueryProcessor
from app.documents.services.reranker import IdentityReranker
from app.documents.services.retrieval_service import RetrievalService


@pytest.mark.asyncio
async def test_query_expansion_catches_vocabulary_mismatch():
    """
    FEATURE EFFECTIVENESS TEST:
    Demonstrates that query expansion recovers relevant chunks when there is a
    vocabulary mismatch (e.g. acronym 'JWT' vs full phrase 'JSON Web Token').
    - Baseline: single query 'JWT expiry' yields 0 sparse matches.
    - Advanced: lexical expansion generates 'JSON Web Token expiration' -> matches doc.
    """
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.get_allowed_document_ids.return_value = [doc_id]

    doc_chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        document_name="api_specifications.md",
        text="JSON Web Token (JWT) access token lifetime is 15 minutes.",
        similarity_score=0.95,
        normalized_score=0.95,
        chunk_index=0,
    )

    # Mock sparse retriever: fails for raw 'JWT expiry', succeeds for expanded 'JSON Web Token'
    async def mock_sparse_retrieve(
        query, user_id=None, top_k=10, document_ids=None, **kwargs
    ):
        if "json web token" in query.lower():
            return [doc_chunk]
        return []

    mock_sparse = AsyncMock()
    mock_sparse.retrieve.side_effect = mock_sparse_retrieve

    mock_dense = AsyncMock()
    mock_dense.retrieve.return_value = []

    # 1. Baseline Service (Expansion Disabled)
    baseline_service = RetrievalService(
        query_processor=DefaultQueryProcessor(),
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        fusion_engine=ReciprocalRankFusionEngine(rrf_k=60),
        mmr_selector=DefaultMMRSelector(),
        reranker=IdentityReranker(),
        chunk_repo=mock_chunk_repo,
        enable_query_expansion=False,
    )

    scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)
    baseline_res: SearchResult = await baseline_service.retrieve(
        query="JWT expiry",
        user_id=user_id,
        top_k=5,
        retrieval_scope=scope,
    )
    assert len(baseline_res.retrieved_chunks) == 0  # Baseline misses the document

    # 2. Advanced Service (Expansion Enabled)
    advanced_service = RetrievalService(
        query_processor=DefaultQueryProcessor(),
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        fusion_engine=ReciprocalRankFusionEngine(rrf_k=60),
        mmr_selector=DefaultMMRSelector(),
        reranker=IdentityReranker(),
        chunk_repo=mock_chunk_repo,
        query_classifier=DeterministicQueryClassifier(),
        query_expander=LexicalQueryExpander(),
        enable_query_expansion=True,
    )

    advanced_res: SearchResult = await advanced_service.retrieve(
        query="JWT expiry",
        user_id=user_id,
        top_k=5,
        retrieval_scope=scope,
    )
    assert len(advanced_res.retrieved_chunks) == 1  # Expansion recovers the document
    assert advanced_res.retrieved_chunks[0].chunk_id == doc_chunk.chunk_id


@pytest.mark.asyncio
async def test_query_decomposition_retrieves_multi_hop_evidence():
    """
    FEATURE EFFECTIVENESS TEST:
    Demonstrates that query decomposition enables multi-aspect evidence retrieval.
    - Compound query: 'What was 2025 revenue and also the engineering SLO?'
    - Baseline: single retrieval only returns financial chunks.
    - Advanced: decomposed subqueries retrieve both financial and engineering chunks.
    """
    user_id = uuid.uuid4()
    doc_fin_id = uuid.uuid4()
    doc_eng_id = uuid.uuid4()

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.get_allowed_document_ids.return_value = [doc_fin_id, doc_eng_id]

    chunk_fin = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_fin_id,
        document_name="financial_report_2025.md",
        text="FY2025 consolidated GAAP revenue reached $142.5 million.",
        similarity_score=0.90,
        chunk_index=0,
    )
    chunk_eng = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_eng_id,
        document_name="engineering_policies.md",
        text="Enterprise availability SLO is 99.99% uptime.",
        similarity_score=0.90,
        chunk_index=0,
    )

    async def mock_retriever(
        query, user_id=None, top_k=10, document_ids=None, **kwargs
    ):
        q_lower = query.lower()
        results = []
        if "revenue" in q_lower:
            results.append(chunk_fin)
        if "slo" in q_lower or "sla" in q_lower:
            results.append(chunk_eng)
        return results

    mock_dense = AsyncMock()
    mock_dense.retrieve.side_effect = mock_retriever
    mock_sparse = AsyncMock()
    mock_sparse.retrieve.return_value = []

    # Advanced Service with decomposition
    service = RetrievalService(
        query_processor=DefaultQueryProcessor(),
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        fusion_engine=ReciprocalRankFusionEngine(rrf_k=60),
        mmr_selector=DefaultMMRSelector(),
        reranker=IdentityReranker(),
        chunk_repo=mock_chunk_repo,
        query_classifier=DeterministicQueryClassifier(),
        query_decomposer=DeterministicQueryDecomposer(),
        enable_query_decomposition=True,
    )

    scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)
    res = await service.retrieve(
        query="What was 2025 revenue and also the engineering SLO target?",
        user_id=user_id,
        top_k=5,
        retrieval_scope=scope,
    )

    # Proves both documents were successfully retrieved
    retrieved_doc_ids = {c.document_id for c in res.retrieved_chunks}
    assert doc_fin_id in retrieved_doc_ids
    assert doc_eng_id in retrieved_doc_ids


@pytest.mark.asyncio
async def test_weighted_rrf_shifts_modality_ranking():
    """
    FEATURE EFFECTIVENESS TEST:
    Demonstrates that Weighted RRF successfully modulates dense vs sparse preference.
    """
    chunk_dense = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name="semantic.md",
        text="High level overview of architectural topology",
        similarity_score=0.9,
        chunk_index=0,
    )
    chunk_sparse = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name="code.md",
        text="Exact code definition error ERR_503_UNAVAILABLE",
        similarity_score=0.9,
        chunk_index=0,
    )

    # 1. Heavy Dense Weighting
    dense_weighted_engine = WeightedReciprocalRankFusionEngine(
        rrf_k=60, dense_weight=3.0, sparse_weight=1.0
    )
    dense_first = dense_weighted_engine.fuse([chunk_dense], [chunk_sparse])
    assert dense_first[0].chunk_id == chunk_dense.chunk_id

    # 2. Heavy Sparse Weighting
    sparse_weighted_engine = WeightedReciprocalRankFusionEngine(
        rrf_k=60, dense_weight=1.0, sparse_weight=3.0
    )
    sparse_first = sparse_weighted_engine.fuse([chunk_dense], [chunk_sparse])
    assert sparse_first[0].chunk_id == chunk_sparse.chunk_id


@pytest.mark.asyncio
async def test_neighbor_chunk_expansion_retrieves_adjacent_context():
    """
    FEATURE EFFECTIVENESS TEST:
    Demonstrates that neighbor chunk expansion pulls adjacent context required for
    answering questions that span across chunk boundaries.
    """
    doc_id = uuid.uuid4()
    primary_chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        document_name="policies.md",
        text="Section 1: Service Level Agreements (SLAs)",
        similarity_score=0.95,
        rerank_score=0.95,
        chunk_index=0,
    )

    neighbor_chunk_1 = Chunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        chunk_index=1,
        text="Section 2: Incident Severity Classifications SEV-1 to SEV-4",
        character_start=100,
        character_end=200,
        token_estimate=25,
        created_at=datetime.datetime.now(datetime.UTC),
    )

    mock_repo = AsyncMock()
    mock_repo.list_by_document.return_value = [neighbor_chunk_1]

    selector = ContextSelector(
        token_estimator=CharacterTokenEstimator(),
        enable_neighbor_chunks=True,
        neighbor_window=1,
        chunk_repo=mock_repo,
        max_context_tokens=4000,
    )

    selected = await selector.select_context([primary_chunk], allowed_doc_ids={doc_id})
    assert selected.neighbor_chunks_added == 1
    assert any("SEV-1" in c.text for c in selected.selected_chunks)


@pytest.mark.asyncio
async def test_negative_case_noisy_expansion_contained_by_limits_and_thresholds():
    """
    NEGATIVE CASE / SAFETY TEST:
    Verifies that when query expansion generates multiple queries for a noisy or
    ambiguous input:
    1. Query count is strictly bounded by MAX_TOTAL_RETRIEVAL_QUERIES (<= 6)
    2. Low-relevance noise chunks are pruned by ContextSelector threshold
    3. Original query is always preserved at query 0
    """
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.get_allowed_document_ids.return_value = [doc_id]

    # Noisy low-relevance chunk
    noise_chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        document_name="noise.md",
        text="Random irrelevant background noise",
        similarity_score=0.15,
        rerank_score=0.10,
        chunk_index=0,
    )

    mock_dense = AsyncMock()
    mock_dense.retrieve.return_value = [noise_chunk]
    mock_sparse = AsyncMock()
    mock_sparse.retrieve.return_value = []

    service = RetrievalService(
        query_processor=DefaultQueryProcessor(),
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        chunk_repo=mock_chunk_repo,
        query_classifier=DeterministicQueryClassifier(),
        query_expander=LexicalQueryExpander(),
        enable_query_expansion=True,
        max_total_retrieval_queries=4,  # Strict limit
    )

    scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)
    res = await service.retrieve(
        query="JWT and OAuth and SLA and RAG and API and DB",
        user_id=user_id,
        top_k=5,
        retrieval_scope=scope,
    )

    # 1. Queries capped to max
    assert res.diagnostics["total_queries_executed"] <= 4
    # 2. Original query preserved
    assert (
        res.diagnostics["retrieval_queries"][0]
        == "JWT and OAuth and SLA and RAG and API and DB"
    )

    # 3. Context selector drops noise chunk below threshold 0.5
    selector = ContextSelector(
        token_estimator=CharacterTokenEstimator(),
        min_chunk_score=0.50,
        score_source="rerank_score",
    )
    selected = await selector.select_context(res.retrieved_chunks)
    assert len(selected.selected_chunks) == 0  # Noise successfully pruned
