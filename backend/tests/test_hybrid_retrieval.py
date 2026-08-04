from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from app.documents.domain.interfaces import ChunkRepository
from app.documents.domain.models import Chunk, RetrievalMode, RetrievedChunk
from app.documents.services.fusion import ReciprocalRankFusionEngine
from app.documents.services.index_cache import InMemoryIndexCache
from app.documents.services.mmr import DefaultMMRSelector
from app.documents.services.query_processor import DefaultQueryProcessor
from app.documents.services.reranker import IdentityReranker
from app.documents.services.retrieval_service import RetrievalService
from app.documents.services.sparse_index import InMemoryBM25Index
from app.documents.services.sparse_retriever import BM25Retriever


# --- 1. QueryProcessor Tests ---
def test_query_processor_normalization_and_stats():
    acronyms = {"rag": "retrieval augmented generation", "llm": "large language model"}
    typos = {"searc": "search", "retreival": "retrieval"}
    processor = DefaultQueryProcessor(acronyms=acronyms, typos=typos)

    # Test query with typos and acronyms
    query = "  My Retreival RAG searc!  "
    processed = processor.process(query)

    # Cleaned query (dense): typos corrected, punctuation removed, lowercased, NO acronym expansion
    assert processed.cleaned_query == "my retrieval rag search"
    # Expanded query (sparse): typos corrected, lowercased, AND acronyms expanded
    assert (
        processed.expanded_query == "my retrieval retrieval augmented generation search"
    )
    assert processed.original_query == query

    # Statistics check
    stats = processed.stats
    assert stats.original_length == len(query)
    assert stats.cleaned_length == len(processed.cleaned_query)
    assert stats.word_count == 4
    assert stats.char_count == len(processed.cleaned_query)
    assert stats.has_typos_corrected is True
    assert stats.has_acronyms_expanded is True
    assert stats.corrections_count == 2  # retreival -> retrieval, searc -> search
    assert stats.expansions_count == 1  # rag -> retrieval augmented generation
    assert stats.processing_time_ms > 0.0


# --- 2. IndexCache Tests ---
def test_index_cache_operations():
    cache = InMemoryIndexCache()
    user_id = uuid4()
    stats = {"count": 10, "max_created_at": datetime.now(UTC)}
    index_data = "mock_bm25_instance"

    assert cache.get(user_id) is None
    assert cache.get_stats(user_id) is None

    cache.set(user_id, index_data, stats)
    assert cache.get(user_id) == "mock_bm25_instance"
    assert cache.get_stats(user_id) == stats

    cache.invalidate(user_id)
    assert cache.get(user_id) is None
    assert cache.get_stats(user_id) is None


# --- 3. SparseIndex & BM25Retriever Tests ---
@pytest.mark.asyncio
async def test_sparse_index_build_and_search():
    user_id = uuid4()
    doc_id = uuid4()
    chunk_repo = MagicMock(spec=ChunkRepository)
    cache = InMemoryIndexCache()

    # 1. Setup mock chunks
    chunk1 = Chunk(
        id=uuid4(),
        document_id=doc_id,
        chunk_index=0,
        text="The quick brown fox jumps over the lazy dog",
        character_start=0,
        character_end=43,
        token_estimate=10,
        metadata={
            "tags": ["animals", "quick"],
            "category": "nature",
            "document_name": "fox.txt",
        },
        created_at=datetime.now(UTC),
    )
    chunk2 = Chunk(
        id=uuid4(),
        document_id=doc_id,
        chunk_index=1,
        text="Retrieval augmented generation systems combine dense and sparse search",
        character_start=0,
        character_end=70,
        token_estimate=12,
        metadata={
            "tags": ["search", "systems"],
            "category": "tech",
            "document_name": "rag.txt",
        },
        created_at=datetime.now(UTC),
    )

    db_chunks = [chunk1, chunk2]
    db_stats = {"count": 2, "max_created_at": chunk2.created_at}

    chunk_repo.get_chunks_metadata_stats = AsyncMock(return_value=db_stats)
    chunk_repo.get_filtered_chunks = AsyncMock(return_value=db_chunks)

    sparse_index = InMemoryBM25Index(chunk_repo, cache)
    retriever = BM25Retriever(sparse_index)

    # 2. Test search (triggers index build first time)
    results = await retriever.retrieve(
        query="retrieval augmented generation",
        user_id=user_id,
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].chunk_id == chunk2.id
    assert results[0].document_name == "rag.txt"
    assert results[0].similarity_score > 0.0

    # Ensure repository was called to fetch and build index
    assert chunk_repo.get_chunks_metadata_stats.call_count == 1
    assert chunk_repo.get_filtered_chunks.call_count == 1

    # 3. Test caching (subsequent search should hit cache and not reload from DB)
    results2 = await retriever.retrieve(
        query="quick brown fox",
        user_id=user_id,
        top_k=5,
    )
    assert len(results2) == 1
    assert results2[0].chunk_id == chunk1.id
    assert (
        chunk_repo.get_filtered_chunks.call_count == 1
    )  # Still 1, did not call DB again!

    # 4. Test filtering by tags
    results_tag = await retriever.retrieve(
        query="retrieval augmented generation",
        user_id=user_id,
        top_k=5,
        tags=["systems"],
    )
    assert len(results_tag) == 1
    assert results_tag[0].chunk_id == chunk2.id

    results_tag_miss = await retriever.retrieve(
        query="retrieval augmented generation",
        user_id=user_id,
        top_k=5,
        tags=["animals"],  # No matching tags
    )
    assert len(results_tag_miss) == 0

    # 5. Test filtering by metadata
    results_meta = await retriever.retrieve(
        query="retrieval",
        user_id=user_id,
        top_k=5,
        filter_metadata={"category": "tech"},
    )
    assert len(results_meta) == 1
    assert results_meta[0].chunk_id == chunk2.id

    # 6. Drift detection: change count and check rebuild is triggered
    new_stats = {"count": 3, "max_created_at": datetime.now(UTC)}
    chunk_repo.get_chunks_metadata_stats.return_value = new_stats
    chunk3 = Chunk(
        id=uuid4(),
        document_id=doc_id,
        chunk_index=2,
        text="A third chunk about search engines",
        character_start=0,
        character_end=34,
        token_estimate=6,
        metadata={"document_name": "third.txt"},
        created_at=new_stats["max_created_at"],
    )
    chunk_repo.get_filtered_chunks.return_value = [chunk1, chunk2, chunk3]

    results3 = await retriever.retrieve(
        query="engines",
        user_id=user_id,
        top_k=5,
    )
    assert len(results3) == 1
    assert results3[0].chunk_id == chunk3.id
    # get_filtered_chunks count increases to 2 because drift triggered rebuild!
    assert chunk_repo.get_filtered_chunks.call_count == 2


# --- 4. Fusion Engine Tests ---
def test_reciprocal_rank_fusion():
    engine = ReciprocalRankFusionEngine(rrf_k=60)
    doc_id = uuid4()

    c1 = RetrievedChunk(
        chunk_id=UUID("11111111-1111-1111-1111-111111111111"),
        document_id=doc_id,
        document_name="doc.txt",
        text="chunk 1 text",
        similarity_score=0.9,
        normalized_score=0.9,
        chunk_index=0,
    )
    c2 = RetrievedChunk(
        chunk_id=UUID("22222222-2222-2222-2222-222222222222"),
        document_id=doc_id,
        document_name="doc.txt",
        text="chunk 2 text",
        similarity_score=0.8,
        normalized_score=0.8,
        chunk_index=1,
    )
    c3 = RetrievedChunk(
        chunk_id=UUID("33333333-3333-3333-3333-333333333333"),
        document_id=doc_id,
        document_name="doc.txt",
        text="chunk 3 text",
        similarity_score=0.7,
        normalized_score=0.7,
        chunk_index=2,
    )

    # Dense results: c1 (rank 1), c2 (rank 2)
    dense = [c1, c2]
    # Sparse results: c3 (rank 1), c1 (rank 2)
    sparse = [c3, c1]

    # RRF scores should be:
    # c1: 1/(1+60) + 1/(2+60) = 1/61 + 1/62 = 0.01639 + 0.01613 = 0.03252
    # c2: 1/(2+60) = 1/62 = 0.01613
    # c3: 1/(1+60) = 1/61 = 0.01639
    # Ordering: c1, c3, c2
    fused = engine.fuse(dense, sparse)

    assert len(fused) == 3
    assert fused[0].chunk_id == c1.chunk_id
    assert fused[1].chunk_id == c3.chunk_id
    assert fused[2].chunk_id == c2.chunk_id

    # Raw scores checked (not normalized)
    assert fused[0].similarity_score == pytest.approx(0.03252, rel=1e-3)
    assert fused[0].normalized_score is None


# --- 5. MMR Selector Tests ---
def test_mmr_selector_diversity():
    selector = DefaultMMRSelector()
    doc_id = uuid4()

    c1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="deep learning and neural networks",
        similarity_score=0.9,
        normalized_score=0.9,
        chunk_index=0,
    )
    c2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="deep learning and neural networks",  # Identical to c1 (duplicate)
        similarity_score=0.88,
        normalized_score=0.88,
        chunk_index=1,
    )
    c3 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="reinforcement learning and robot control",  # Diverse
        similarity_score=0.7,
        normalized_score=0.7,
        chunk_index=2,
    )

    # With lambda = 0.5:
    # First selected: c1
    # Next, score c2 vs selected:
    #   sim1 = 0.88
    #   sim2 = jaccard(c2, c1) -> extremely high
    #   mmr_score = 0.5 * 0.88 - 0.5 * high_val -> very low
    # Score c3 vs selected:
    #   sim1 = 0.7
    #   sim2 = jaccard(c3, c1) -> very low
    #   mmr_score = 0.5 * 0.7 - 0.5 * low_val -> higher than c2
    # So c3 should be selected second over c2!
    selected = selector.select([c1, c2, c3], top_k=2, mmr_lambda=0.5)

    assert len(selected) == 2
    assert selected[0].chunk_id == c1.chunk_id
    assert selected[1].chunk_id == c3.chunk_id


def test_mmr_selector_pluggable_similarity():
    selector = DefaultMMRSelector()
    doc_id = uuid4()

    c1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="text one",
        similarity_score=0.9,
        normalized_score=0.9,
        chunk_index=0,
    )
    c2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc.txt",
        text="text two",
        similarity_score=0.8,
        normalized_score=0.8,
        chunk_index=1,
    )

    # Custom mock cosine similarity function returning high overlap (1.0)
    mock_similarity_fn = MagicMock(return_value=1.0)

    selected = selector.select(
        [c1, c2], top_k=2, mmr_lambda=0.5, similarity_fn=mock_similarity_fn
    )
    assert len(selected) == 2
    mock_similarity_fn.assert_called_once_with(c2, c1)


# --- 6. IdentityReranker Tests ---
def test_identity_reranker():
    reranker = IdentityReranker()
    doc_id = uuid4()
    chunks = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_name="doc.txt",
            text="A",
            similarity_score=0.9,
            chunk_index=0,
        ),
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_name="doc.txt",
            text="B",
            similarity_score=0.8,
            chunk_index=1,
        ),
    ]

    reranked = reranker.rerank("query", chunks)
    assert reranked == chunks  # No changes


# --- 7. Orchestration & Integration Tests ---
@pytest.mark.asyncio
async def test_retrieval_orchestrator_integration(mocker):
    # Setup mocks
    processor = MagicMock()
    processor.process.return_value.query = "processed query"
    processor.process.return_value.cleaned_query = "cleaned query"
    processor.process.return_value.expanded_query = "expanded query"

    dense_retriever = MagicMock()
    dense_result = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_name="dense.txt",
            text="dense context",
            similarity_score=0.85,
            normalized_score=0.85,
            chunk_index=0,
        )
    ]
    dense_retriever.retrieve = AsyncMock(return_value=dense_result)

    sparse_retriever = MagicMock()
    sparse_result = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_name="sparse.txt",
            text="sparse context",
            similarity_score=0.6,
            normalized_score=0.6,
            chunk_index=0,
        )
    ]
    sparse_retriever.retrieve = AsyncMock(return_value=sparse_result)

    fusion_engine = MagicMock()
    fused_chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_name="fused.txt",
        text="fused text",
        similarity_score=0.03,
        normalized_score=None,
        chunk_index=0,
    )
    fusion_engine.fuse.return_value = [fused_chunk]

    mmr_selector = MagicMock()
    mmr_selector.select.side_effect = lambda chunks, top_k, **kwargs: chunks[:top_k]

    reranker = MagicMock()
    reranker.rerank.side_effect = lambda _query, chunks: chunks

    chunk_repo = MagicMock()
    chunk_repo.verify_document_ownership = AsyncMock(return_value=True)

    # Initialize Service
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
        vector_top_k=10,
        bm25_top_k=10,
        mmr_lambda=0.5,
        rerank_top_k=5,
    )

    user_id = uuid4()
    # Execute retrieve in hybrid mode
    result = await service.retrieve(
        query="hybrid search",
        user_id=user_id,
        top_k=2,
        retrieval_mode=RetrievalMode.HYBRID,
    )

    # Verify calls
    processor.process.assert_called_once_with("hybrid search")
    dense_retriever.retrieve.assert_called_once_with(
        query="cleaned query",
        user_id=user_id,
        top_k=10,
        document_ids=None,
        tags=None,
        filter_metadata=None,
    )
    sparse_retriever.retrieve.assert_called_once_with(
        query="expanded query",
        user_id=user_id,
        top_k=10,
        document_ids=None,
        tags=None,
        filter_metadata=None,
    )
    fusion_engine.fuse.assert_called_once_with(dense_result, sparse_result)
    mmr_selector.select.assert_called_once_with(
        chunks=[fused_chunk],
        top_k=2,
        mmr_lambda=0.5,
    )
    reranker.rerank.assert_called_once_with("cleaned query", [fused_chunk])

    # Result structure verification
    assert result.original_query == "hybrid search"
    assert result.retrieval_strategy == RetrievalMode.HYBRID
    assert result.fusion_method == "RRF"
    assert len(result.retrieved_chunks) == 1
    assert result.retrieved_chunks[0].text == "fused text"
    assert result.dense_matches == dense_result
    assert result.sparse_matches == sparse_result
    assert result.reranker is not None
