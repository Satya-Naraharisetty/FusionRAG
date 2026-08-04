import asyncio
import logging
import time
from typing import Any
from uuid import UUID

from app.documents.domain.exceptions import UnauthorizedDocumentAccess
from app.documents.domain.interfaces import (
    ChunkRepository,
    DenseRetriever,
    FusionEngine,
    MMRSelector,
    QueryProcessor,
    Reranker,
    SparseRetriever,
)
from app.documents.domain.models import (
    FusionMethod,
    RerankerName,
    RetrievalMode,
    SearchResult,
)

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    RetrievalService coordinates the hybrid search pipeline.
    It processes query using QueryProcessor, runs dense and sparse retrieval concurrently,
    fuses the results using Reciprocal Rank Fusion, applies MMR diversity selection,
    and runs the final reranker, returning a structured SearchResult.
    """

    def __init__(
        self,
        query_processor: QueryProcessor | None = None,
        dense_retriever: DenseRetriever | None = None,
        sparse_retriever: SparseRetriever | None = None,
        fusion_engine: FusionEngine | None = None,
        mmr_selector: MMRSelector | None = None,
        reranker: Reranker | None = None,
        chunk_repo: ChunkRepository | None = None,
        # Backwards compatible parameters for old construction in tests
        embedding_generator: Any | None = None,
        vector_store: Any | None = None,
        ranker: Any | None = None,
        similarity_threshold: float = 0.25,
        search_timeout: float = 3.0,
        # New configurable parameters with default settings fallback
        enable_hybrid_search: bool | None = None,
        enable_mmr: bool | None = None,
        enable_reranker: bool | None = None,
        vector_top_k: int | None = None,
        bm25_top_k: int | None = None,
        mmr_lambda: float | None = None,
        rerank_top_k: int | None = None,
    ) -> None:
        from app.core.config import settings

        # Detect if we are running in legacy/backwards-compatible fallback mode
        is_legacy = (embedding_generator is not None or vector_store is not None) and (
            query_processor is None
        )

        # Load configurations with settings fallback
        self._enable_hybrid_search = (
            enable_hybrid_search
            if enable_hybrid_search is not None
            else (
                False if is_legacy else getattr(settings, "ENABLE_HYBRID_SEARCH", True)
            )
        )
        self._enable_mmr = (
            enable_mmr
            if enable_mmr is not None
            else (False if is_legacy else getattr(settings, "ENABLE_MMR", True))
        )
        self._enable_reranker = (
            enable_reranker
            if enable_reranker is not None
            else (False if is_legacy else getattr(settings, "ENABLE_RERANKER", True))
        )
        self._vector_top_k = (
            vector_top_k
            if vector_top_k is not None
            else getattr(settings, "VECTOR_TOP_K", 20)
        )
        self._bm25_top_k = (
            bm25_top_k
            if bm25_top_k is not None
            else getattr(settings, "BM25_TOP_K", 20)
        )
        self._mmr_lambda = (
            mmr_lambda
            if mmr_lambda is not None
            else getattr(settings, "MMR_LAMBDA", 0.5)
        )
        self._rerank_top_k = (
            rerank_top_k
            if rerank_top_k is not None
            else getattr(settings, "RERANK_TOP_K", 5)
        )

        # 1. Chunk Repository
        self._chunk_repo = chunk_repo

        # 2. Query Processor
        if query_processor:
            self._query_processor = query_processor
        else:
            from app.documents.services.query_processor import DefaultQueryProcessor

            self._query_processor = DefaultQueryProcessor()

        # 3. Dense Retriever
        if dense_retriever:
            self._dense_retriever = dense_retriever
        elif embedding_generator and vector_store and chunk_repo:
            from app.documents.services.dense_retriever import QdrantDenseRetriever

            self._dense_retriever = QdrantDenseRetriever(
                embedding_generator=embedding_generator,
                vector_store=vector_store,
                chunk_repo=chunk_repo,
                similarity_threshold=similarity_threshold,
                search_timeout=search_timeout,
            )
        else:
            self._dense_retriever = None

        # 4. Sparse Retriever
        if sparse_retriever:
            self._sparse_retriever = sparse_retriever
        elif chunk_repo:
            from app.documents.services.index_cache import InMemoryIndexCache
            from app.documents.services.sparse_index import InMemoryBM25Index
            from app.documents.services.sparse_retriever import BM25Retriever

            # Construct a default cache and index since we are in fallback constructor
            cache = InMemoryIndexCache()
            sparse_index = InMemoryBM25Index(chunk_repo=chunk_repo, index_cache=cache)
            self._sparse_retriever = BM25Retriever(sparse_index=sparse_index)
        else:
            self._sparse_retriever = None

        # 5. Fusion Engine
        if fusion_engine:
            self._fusion_engine = fusion_engine
        else:
            from app.documents.services.fusion import ReciprocalRankFusionEngine

            self._fusion_engine = ReciprocalRankFusionEngine(
                rrf_k=getattr(settings, "RRF_K", 60)
            )

        # 6. MMR Selector
        if mmr_selector:
            self._mmr_selector = mmr_selector
        else:
            from app.documents.services.mmr import DefaultMMRSelector

            self._mmr_selector = DefaultMMRSelector()

        # 7. Reranker
        if reranker:
            self._reranker = reranker
        else:
            from app.documents.services.reranker import IdentityReranker

            self._reranker = IdentityReranker()

        # Backwards compatible ranker fallback if someone calls self._ranker (or tests mock it)
        self._ranker = ranker

    async def retrieve(
        self,
        query: str,
        user_id: UUID,
        top_k: int,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        retrieval_mode: RetrievalMode | str | None = None,
    ) -> SearchResult:
        start_time = time.perf_counter()

        # 1. Ownership Verification (Never trust incoming document IDs)
        if document_ids:
            unique_doc_ids = list(set(document_ids))
            ownership_ok = await self._chunk_repo.verify_document_ownership(
                unique_doc_ids, user_id
            )
            if not ownership_ok:
                raise UnauthorizedDocumentAccess(
                    "Unauthorized document access: one or more specified document IDs do not belong to you."
                )
        else:
            unique_doc_ids = None

        # 2. Query Preprocessing
        processed_query_obj = self._query_processor.process(query)

        # Determine retrieval mode: "semantic", "sparse", "hybrid", "auto"
        if not retrieval_mode:
            retrieval_mode = (
                RetrievalMode.HYBRID
                if self._enable_hybrid_search
                else RetrievalMode.SEMANTIC
            )
        elif isinstance(retrieval_mode, str):
            try:
                retrieval_mode = RetrievalMode(retrieval_mode.lower())
            except ValueError:
                retrieval_mode = (
                    RetrievalMode.HYBRID
                    if self._enable_hybrid_search
                    else RetrievalMode.SEMANTIC
                )

        # Auto Mode Strategy:
        # Default to hybrid if hybrid search is enabled, else semantic.
        if retrieval_mode == RetrievalMode.AUTO:
            retrieval_mode = (
                RetrievalMode.HYBRID
                if self._enable_hybrid_search
                else RetrievalMode.SEMANTIC
            )

        # 3. Concurrent Retrieval
        dense_results = []
        sparse_results = []

        dense_latency = 0.0
        sparse_latency = 0.0

        # Adjust top_k values for retrievers
        v_top_k = (
            self._vector_top_k if retrieval_mode == RetrievalMode.HYBRID else top_k
        )
        s_top_k = self._bm25_top_k if retrieval_mode == RetrievalMode.HYBRID else top_k

        async def run_dense():
            nonlocal dense_latency, dense_results
            if (
                retrieval_mode in (RetrievalMode.SEMANTIC, RetrievalMode.HYBRID)
                and self._dense_retriever
            ):
                t0 = time.perf_counter()
                dense_results = await self._dense_retriever.retrieve(
                    query=processed_query_obj.cleaned_query,
                    user_id=user_id,
                    top_k=v_top_k,
                    document_ids=unique_doc_ids,
                    tags=tags,
                    filter_metadata=filter_metadata,
                )
                dense_latency = time.perf_counter() - t0

        async def run_sparse():
            nonlocal sparse_latency, sparse_results
            if (
                retrieval_mode in (RetrievalMode.SPARSE, RetrievalMode.HYBRID)
                and self._sparse_retriever
            ):
                t0 = time.perf_counter()
                sparse_results = await self._sparse_retriever.retrieve(
                    query=processed_query_obj.expanded_query,
                    user_id=user_id,
                    top_k=s_top_k,
                    document_ids=unique_doc_ids,
                    tags=tags,
                    filter_metadata=filter_metadata,
                )
                sparse_latency = time.perf_counter() - t0

        # Execute concurrent tasks
        await asyncio.gather(run_dense(), run_sparse())

        # 4. Fusion Engine
        fused_results = []
        fusion_latency = 0.0
        fusion_method = None

        if retrieval_mode == RetrievalMode.HYBRID:
            t0 = time.perf_counter()
            fused_results = self._fusion_engine.fuse(dense_results, sparse_results)
            fusion_latency = time.perf_counter() - t0
            fusion_method = FusionMethod.RRF
        elif retrieval_mode == RetrievalMode.SEMANTIC:
            fused_results = dense_results
        else:  # SPARSE
            fused_results = sparse_results

        # 5. MMR Diversity Selection
        final_results = fused_results
        # Apply MMR if enabled
        if self._enable_mmr:
            final_results = self._mmr_selector.select(
                chunks=fused_results,
                top_k=top_k,
                mmr_lambda=self._mmr_lambda,
            )
        else:
            final_results = fused_results[:top_k]

        # 6. Reranking
        reranked_results = final_results
        rerank_latency = 0.0
        if self._enable_reranker:
            t0 = time.perf_counter()
            # If a custom legacy ranker was supplied in constructor, use it for backwards compatibility,
            # otherwise use Reranker
            if self._ranker:
                reranked_results = self._ranker.rank(
                    processed_query_obj.cleaned_query, final_results
                )
            else:
                reranked_results = self._reranker.rerank(
                    processed_query_obj.cleaned_query, final_results
                )
            reranked_results = reranked_results[: self._rerank_top_k]
            rerank_latency = time.perf_counter() - t0

        end_time = time.perf_counter()
        total_latency = end_time - start_time

        # Observability Logging (Never log document contents)
        logger.info(
            f"Retrieval stats [mode: {retrieval_mode.value}] - "
            f"dense_latency: {dense_latency:.4f}s (count: {len(dense_results)}), "
            f"sparse_latency: {sparse_latency:.4f}s (count: {len(sparse_results)}), "
            f"fusion_latency: {fusion_latency:.4f}s (fused: {len(fused_results)}), "
            f"rerank_latency: {rerank_latency:.4f}s (final: {len(reranked_results)}), "
            f"total_latency: {total_latency:.4f}s"
        )

        return SearchResult(
            original_query=query,
            retrieval_time=total_latency,
            total_matches=len(reranked_results),
            retrieved_chunks=reranked_results,
            search_strategy=retrieval_mode.value,
            retrieval_strategy=retrieval_mode,
            dense_matches=dense_results,
            sparse_matches=sparse_results,
            fusion_method=fusion_method,
            reranker=(
                RerankerName(type(self._reranker).__name__)
                if self._enable_reranker
                and type(self._reranker).__name__ in RerankerName._value2member_map_
                else None
            ),
        )
