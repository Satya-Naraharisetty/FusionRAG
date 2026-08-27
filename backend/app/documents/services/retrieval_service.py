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
    IndexCache,
    MMRSelector,
    QueryProcessor,
    Reranker,
    SparseRetriever,
)
from app.documents.domain.models import (
    DocumentRetrievalScope,
    FusionMethod,
    RerankerName,
    RetrievalMode,
    RetrievedChunk,
    SearchResult,
)
from app.documents.services.fusion import (
    ReciprocalRankFusionEngine,
    WeightedReciprocalRankFusionEngine,
)
from app.documents.services.query_classifier import (
    DeterministicQueryClassifier,
    QueryClassification,
    QueryClassifier,
)
from app.documents.services.query_decomposer import (
    DeterministicQueryDecomposer,
    QueryDecomposer,
    SafeQueryDecomposer,
)
from app.documents.services.query_expansion import (
    LexicalQueryExpander,
    QueryExpander,
    SafeQueryExpander,
)

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    RetrievalService coordinates the hybrid retrieval pipeline.
    In baseline mode, executes single-query Dense + BM25 retrieval, RRF fusion, MMR, and Cross-Encoder reranking.
    In advanced mode, orchestrates query classification, conservative decomposition,
    lexical/semantic expansion, concurrent multi-query retrieval, weighted RRF, and canonical deduplication.
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
        index_cache: IndexCache | None = None,
        empty_kb_cache_ttl_seconds: float | None = None,
        # Backwards compatible parameters for old construction in tests
        embedding_generator: Any | None = None,
        vector_store: Any | None = None,
        ranker: Any | None = None,
        similarity_threshold: float = 0.25,
        search_timeout: float = 3.0,
        # Configurable hybrid parameters
        enable_hybrid_search: bool | None = None,
        enable_mmr: bool | None = None,
        enable_reranker: bool | None = None,
        vector_top_k: int | None = None,
        bm25_top_k: int | None = None,
        mmr_lambda: float | None = None,
        rerank_top_k: int | None = None,
        # Advanced RAG configurations
        query_classifier: QueryClassifier | None = None,
        query_expander: QueryExpander | None = None,
        query_decomposer: QueryDecomposer | None = None,
        enable_query_classification: bool | None = None,
        enable_query_expansion: bool | None = None,
        enable_query_decomposition: bool | None = None,
        enable_weighted_rrf: bool | None = None,
        dense_weight: float | None = None,
        sparse_weight: float | None = None,
        max_total_retrieval_queries: int | None = None,
        max_retrieval_candidates: int | None = None,
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
        self._empty_kb_cache_ttl_seconds = (
            empty_kb_cache_ttl_seconds
            if empty_kb_cache_ttl_seconds is not None
            else getattr(settings, "EMPTY_KB_CACHE_TTL_SECONDS", 60.0)
        )

        # Advanced Retrieval Feature Flags and Knobs
        self._enable_query_classification = (
            enable_query_classification
            if enable_query_classification is not None
            else getattr(settings, "ENABLE_QUERY_CLASSIFICATION", True)
        )
        self._enable_query_expansion = (
            enable_query_expansion
            if enable_query_expansion is not None
            else getattr(settings, "ENABLE_QUERY_EXPANSION", False)
        )
        self._enable_query_decomposition = (
            enable_query_decomposition
            if enable_query_decomposition is not None
            else getattr(settings, "ENABLE_QUERY_DECOMPOSITION", False)
        )
        self._enable_weighted_rrf = (
            enable_weighted_rrf
            if enable_weighted_rrf is not None
            else getattr(settings, "ENABLE_WEIGHTED_RRF", False)
        )
        self._dense_weight = (
            dense_weight
            if dense_weight is not None
            else getattr(settings, "DENSE_WEIGHT", 1.0)
        )
        self._sparse_weight = (
            sparse_weight
            if sparse_weight is not None
            else getattr(settings, "SPARSE_WEIGHT", 1.0)
        )
        self._max_total_retrieval_queries = (
            max_total_retrieval_queries
            if max_total_retrieval_queries is not None
            else getattr(settings, "MAX_TOTAL_RETRIEVAL_QUERIES", 6)
        )
        self._max_retrieval_candidates = (
            max_retrieval_candidates
            if max_retrieval_candidates is not None
            else getattr(settings, "MAX_RETRIEVAL_CANDIDATES", 100)
        )

        # 1. Chunk Repository & Index Cache
        self._chunk_repo = chunk_repo
        self._index_cache = index_cache
        self._dense_retriever: DenseRetriever | None = None
        self._sparse_retriever: SparseRetriever | None = None

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

        # 4. Sparse Retriever
        if sparse_retriever:
            self._sparse_retriever = sparse_retriever
        elif chunk_repo:
            from app.documents.services.index_cache import InMemoryIndexCache
            from app.documents.services.sparse_index import InMemoryBM25Index
            from app.documents.services.sparse_retriever import BM25Retriever

            cache = index_cache or InMemoryIndexCache()
            if self._index_cache is None:
                self._index_cache = cache
            sparse_index = InMemoryBM25Index(chunk_repo=chunk_repo, index_cache=cache)
            self._sparse_retriever = BM25Retriever(sparse_index=sparse_index)

        # 5. Fusion Engine (Baseline: ReciprocalRankFusionEngine)
        if fusion_engine:
            self._fusion_engine = fusion_engine
        else:
            self._fusion_engine = ReciprocalRankFusionEngine(
                rrf_k=getattr(settings, "RRF_K", 60)
            )

        # Weighted Fusion Engine
        self._weighted_fusion_engine = WeightedReciprocalRankFusionEngine(
            rrf_k=getattr(settings, "RRF_K", 60),
            dense_weight=self._dense_weight,
            sparse_weight=self._sparse_weight,
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

        # 8. Advanced RAG Components
        self._query_classifier = query_classifier or DeterministicQueryClassifier()
        self._query_expander = query_expander or SafeQueryExpander(
            LexicalQueryExpander(),
            timeout_ms=getattr(settings, "QUERY_EXPANSION_TIMEOUT_MS", 500),
            max_queries=getattr(settings, "QUERY_EXPANSION_MAX_QUERIES", 3),
        )
        self._query_decomposer = query_decomposer or SafeQueryDecomposer(
            DeterministicQueryDecomposer(),
            timeout_ms=getattr(settings, "QUERY_DECOMPOSITION_TIMEOUT_MS", 500),
            max_subtasks=getattr(settings, "MAX_QUERY_SUBTASKS", 3),
        )

        # Backwards compatible ranker fallback
        self._ranker = ranker

    async def user_has_chunks(self, user_id: UUID) -> bool:
        if self._chunk_repo is None:
            return True

        if self._index_cache is not None:
            cached_stats = self._index_cache.get_fresh_stats(
                user_id, self._empty_kb_cache_ttl_seconds
            )
            if (
                isinstance(cached_stats, dict)
                and int(cached_stats.get("count") or 0) == 0
            ):
                return False

        try:
            stats = await self._chunk_repo.get_chunks_metadata_stats(user_id)
        except Exception:
            return True

        has_chunks = isinstance(stats, dict) and int(stats.get("count") or 0) > 0
        if not has_chunks and self._index_cache is not None:
            self._index_cache.set(user_id, index_data=None, stats=stats)
        return has_chunks

    async def retrieve(
        self,
        query: str,
        user_id: UUID,
        top_k: int,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        retrieval_mode: RetrievalMode | str | None = None,
        retrieval_scope: DocumentRetrievalScope | None = None,
    ) -> SearchResult:
        start_time = time.perf_counter()

        if self._chunk_repo is None:
            raise RuntimeError(
                "Chunk repository is not configured; cannot verify document ownership."
            )

        if retrieval_scope is None:
            retrieval_scope = DocumentRetrievalScope(
                user_id=user_id,
                conversation_id=None,
                include_conversation_documents=True,
                include_library_documents=True,
                document_ids=document_ids,
                tags=tags,
                filter_metadata=filter_metadata,
            )

        # 1. Resolve and verify allowed document IDs from repository
        allowed_doc_ids = await self._chunk_repo.get_allowed_document_ids(
            retrieval_scope
        )

        if retrieval_scope.document_ids:
            unauthorized = set(retrieval_scope.document_ids) - set(allowed_doc_ids)
            if unauthorized:
                raise UnauthorizedDocumentAccess(
                    "Unauthorized document access: one or more specified document IDs do not belong to you or are not in scope."
                )
            allowed_doc_ids = [
                doc_id
                for doc_id in allowed_doc_ids
                if doc_id in retrieval_scope.document_ids
            ]

        if not allowed_doc_ids:
            logger.info("Retrieval skipped: no documents match the requested scope.")
            ret_strat = RetrievalMode.SEMANTIC
            if retrieval_mode:
                if isinstance(retrieval_mode, str):
                    try:
                        ret_strat = RetrievalMode(retrieval_mode.lower())
                    except ValueError:
                        pass
                else:
                    ret_strat = retrieval_mode
            return SearchResult(
                original_query=query,
                retrieval_time=time.perf_counter() - start_time,
                total_matches=0,
                retrieved_chunks=[],
                search_strategy=ret_strat.value
                if hasattr(ret_strat, "value")
                else str(ret_strat),
                retrieval_strategy=ret_strat,
                dense_matches=[],
                sparse_matches=[],
            )

        # Resolve retrieval mode: "semantic", "sparse", "hybrid", "auto"
        resolved_mode: RetrievalMode
        if not retrieval_mode:
            resolved_mode = (
                RetrievalMode.HYBRID
                if self._enable_hybrid_search
                else RetrievalMode.SEMANTIC
            )
        elif isinstance(retrieval_mode, str):
            try:
                resolved_mode = RetrievalMode(retrieval_mode.lower())
            except ValueError:
                resolved_mode = (
                    RetrievalMode.HYBRID
                    if self._enable_hybrid_search
                    else RetrievalMode.SEMANTIC
                )
        else:
            resolved_mode = retrieval_mode

        if resolved_mode == RetrievalMode.AUTO:
            resolved_mode = (
                RetrievalMode.HYBRID
                if self._enable_hybrid_search
                else RetrievalMode.SEMANTIC
            )

        # -------------------------------------------------------------
        # Branch 1: Baseline Path (Advanced Expansion / Decomposition Disabled)
        # -------------------------------------------------------------
        is_advanced_active = (
            self._enable_query_expansion or self._enable_query_decomposition
        )

        if not is_advanced_active:
            # Standard baseline implementation path
            processed_query_obj = self._query_processor.process(query)

            v_top_k = (
                self._vector_top_k if resolved_mode == RetrievalMode.HYBRID else top_k
            )
            s_top_k = (
                self._bm25_top_k if resolved_mode == RetrievalMode.HYBRID else top_k
            )

            dense_results: list[RetrievedChunk] = []
            sparse_results: list[RetrievedChunk] = []
            dense_latency = 0.0
            sparse_latency = 0.0

            from app.core.telemetry import (
                RETRIEVAL_CANDIDATES_COUNT,
                RETRIEVAL_REQUESTS,
                RETRIEVAL_STAGE_DURATION,
                get_tracer,
            )

            tracer = get_tracer("hybrid-rag.retrieval")

            async def run_dense_baseline():
                nonlocal dense_latency, dense_results
                if (
                    resolved_mode in (RetrievalMode.SEMANTIC, RetrievalMode.HYBRID)
                    and self._dense_retriever
                ):
                    with tracer.start_as_current_span("retrieval.dense_search") as span:
                        t0 = time.perf_counter()
                        dense_results = await self._dense_retriever.retrieve(
                            query=processed_query_obj.cleaned_query,
                            user_id=user_id,
                            top_k=v_top_k,
                            document_ids=allowed_doc_ids,
                            tags=tags,
                            filter_metadata=filter_metadata,
                            retrieval_scope=retrieval_scope,
                        )
                        dense_latency = time.perf_counter() - t0
                        span.set_attribute(
                            "retrieval.candidates_count", len(dense_results)
                        )
                        RETRIEVAL_STAGE_DURATION.labels(stage="dense").observe(
                            dense_latency
                        )
                        RETRIEVAL_CANDIDATES_COUNT.labels(stage="dense").observe(
                            len(dense_results)
                        )

            async def run_sparse_baseline():
                nonlocal sparse_latency, sparse_results
                if (
                    resolved_mode in (RetrievalMode.SPARSE, RetrievalMode.HYBRID)
                    and self._sparse_retriever
                ):
                    with tracer.start_as_current_span(
                        "retrieval.sparse_search"
                    ) as span:
                        t0 = time.perf_counter()
                        sparse_results = await self._sparse_retriever.retrieve(
                            query=processed_query_obj.expanded_query,
                            user_id=user_id,
                            top_k=s_top_k,
                            document_ids=allowed_doc_ids,
                            tags=tags,
                            filter_metadata=filter_metadata,
                            retrieval_scope=retrieval_scope,
                        )
                        sparse_latency = time.perf_counter() - t0
                        span.set_attribute(
                            "retrieval.candidates_count", len(sparse_results)
                        )
                        RETRIEVAL_STAGE_DURATION.labels(stage="sparse").observe(
                            sparse_latency
                        )
                        RETRIEVAL_CANDIDATES_COUNT.labels(stage="sparse").observe(
                            len(sparse_results)
                        )

            await asyncio.gather(run_dense_baseline(), run_sparse_baseline())

            # Fusion Engine
            fused_results: list[RetrievedChunk] = []
            fusion_latency = 0.0
            fusion_method = None

            if resolved_mode == RetrievalMode.HYBRID:
                with tracer.start_as_current_span("retrieval.fusion") as span:
                    t0 = time.perf_counter()
                    if self._enable_weighted_rrf:
                        fused_results = self._weighted_fusion_engine.fuse(
                            dense_results, sparse_results
                        )
                    else:
                        fused_results = self._fusion_engine.fuse(
                            dense_results, sparse_results
                        )
                    fusion_latency = time.perf_counter() - t0
                    fusion_method = FusionMethod.RRF
                    span.set_attribute("fusion.method", "rrf")
                    span.set_attribute("fusion.candidates_count", len(fused_results))
                    RETRIEVAL_STAGE_DURATION.labels(stage="fusion").observe(
                        fusion_latency
                    )
                    RETRIEVAL_CANDIDATES_COUNT.labels(stage="fused").observe(
                        len(fused_results)
                    )
            elif resolved_mode == RetrievalMode.SEMANTIC:
                fused_results = dense_results
            else:  # SPARSE
                fused_results = sparse_results

            # MMR Diversity Selection
            if self._enable_mmr:
                with tracer.start_as_current_span("retrieval.mmr_selection") as span:
                    mmr_results = self._mmr_selector.select(
                        chunks=fused_results,
                        top_k=top_k,
                        mmr_lambda=self._mmr_lambda,
                    )
                    span.set_attribute("mmr.selected_count", len(mmr_results))
            else:
                mmr_results = fused_results[:top_k]

            # Reranking
            reranked_results = mmr_results
            rerank_latency = 0.0
            if self._enable_reranker:
                with tracer.start_as_current_span(
                    "retrieval.cross_encoder_rerank"
                ) as span:
                    t0 = time.perf_counter()
                    if self._ranker:
                        reranked_results = self._ranker.rank(
                            processed_query_obj.cleaned_query, mmr_results
                        )
                    else:
                        reranked_results = await self._reranker.rerank(
                            processed_query_obj.cleaned_query, mmr_results
                        )
                    reranked_results = reranked_results[: self._rerank_top_k]
                    rerank_latency = time.perf_counter() - t0
                    span.set_attribute("rerank.output_count", len(reranked_results))
                    RETRIEVAL_STAGE_DURATION.labels(stage="rerank").observe(
                        rerank_latency
                    )
                    RETRIEVAL_CANDIDATES_COUNT.labels(stage="reranked").observe(
                        len(reranked_results)
                    )

            total_latency = time.perf_counter() - start_time
            try:
                RETRIEVAL_REQUESTS.labels(
                    mode=resolved_mode.value, status="success"
                ).inc()
            except Exception:
                pass

            logger.info(
                f"Retrieval stats [mode: {resolved_mode.value}] - "
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
                search_strategy=resolved_mode.value,
                retrieval_strategy=resolved_mode,
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

        # -------------------------------------------------------------
        # Branch 2: Advanced Multi-Query Retrieval Path
        # -------------------------------------------------------------
        # 1. Query Classification
        classification_start = time.perf_counter()
        classification: QueryClassification = self._query_classifier.classify(query)
        classification_latency = time.perf_counter() - classification_start

        # 2. Derive Query Set (Original query ALWAYS retained at index 0)
        retrieval_queries: list[str] = [query.strip()]
        expansion_latency = 0.0
        decomposition_latency = 0.0
        expanded_queries_list: list[str] = []
        subtask_queries_list: list[str] = []

        # Optional Query Decomposition
        if self._enable_query_decomposition and classification.requires_decomposition:
            t0 = time.perf_counter()
            subtasks = await self._query_decomposer.decompose(
                query, classification.query_type
            )
            decomposition_latency = time.perf_counter() - t0
            for st in subtasks:
                subtask_queries_list.append(st.query)
                if st.query.strip().lower() != query.strip().lower():
                    retrieval_queries.append(st.query.strip())

        # Optional Query Expansion
        if self._enable_query_expansion and (
            classification.requires_expansion
            or not classification.requires_decomposition
        ):
            t0 = time.perf_counter()
            expansions = await self._query_expander.expand(query)
            expansion_latency = time.perf_counter() - t0
            for exp in expansions:
                expanded_queries_list.append(exp)
                if exp.strip().lower() != query.strip().lower():
                    retrieval_queries.append(exp.strip())

        # Deduplicate derived queries while preserving original at index 0
        seen_queries = {query.strip().lower()}
        final_query_set = [query.strip()]
        for q in retrieval_queries[1:]:
            q_lower = q.lower()
            if q_lower not in seen_queries:
                seen_queries.add(q_lower)
                final_query_set.append(q)

        # Hard global query budget enforcement: MAX_TOTAL_RETRIEVAL_QUERIES (original priority)
        final_query_set = final_query_set[: self._max_total_retrieval_queries]

        # 3. Concurrent Multi-Query Retrieval
        retrieval_ops_start = time.perf_counter()
        all_dense_results: list[list[RetrievedChunk]] = []
        all_sparse_results: list[list[RetrievedChunk]] = []

        v_top_k = self._vector_top_k if resolved_mode == RetrievalMode.HYBRID else top_k
        s_top_k = self._bm25_top_k if resolved_mode == RetrievalMode.HYBRID else top_k

        async def fetch_for_query(q_str: str, q_idx: int):
            proc_q = self._query_processor.process(q_str)
            dense_res: list[RetrievedChunk] = []
            sparse_res: list[RetrievedChunk] = []

            async def do_dense():
                nonlocal dense_res
                if (
                    resolved_mode in (RetrievalMode.SEMANTIC, RetrievalMode.HYBRID)
                    and self._dense_retriever
                ):
                    dense_res = await self._dense_retriever.retrieve(
                        query=proc_q.cleaned_query,
                        user_id=user_id,
                        top_k=v_top_k,
                        document_ids=allowed_doc_ids,
                        tags=tags,
                        filter_metadata=filter_metadata,
                        retrieval_scope=retrieval_scope,
                    )
                    # Annotate source query metadata
                    dense_res = [
                        RetrievedChunk(
                            chunk_id=c.chunk_id,
                            document_id=c.document_id,
                            document_name=c.document_name,
                            text=c.text,
                            similarity_score=c.similarity_score,
                            normalized_score=c.normalized_score,
                            rerank_score=c.rerank_score,
                            metadata={
                                **c.metadata,
                                "retrieval_source": f"q{q_idx}_dense",
                                "query_text": q_str,
                            },
                            chunk_index=c.chunk_index,
                        )
                        for c in dense_res
                    ]

            async def do_sparse():
                nonlocal sparse_res
                if (
                    resolved_mode in (RetrievalMode.SPARSE, RetrievalMode.HYBRID)
                    and self._sparse_retriever
                ):
                    sparse_res = await self._sparse_retriever.retrieve(
                        query=proc_q.expanded_query,
                        user_id=user_id,
                        top_k=s_top_k,
                        document_ids=allowed_doc_ids,
                        tags=tags,
                        filter_metadata=filter_metadata,
                        retrieval_scope=retrieval_scope,
                    )
                    # Annotate source query metadata
                    sparse_res = [
                        RetrievedChunk(
                            chunk_id=c.chunk_id,
                            document_id=c.document_id,
                            document_name=c.document_name,
                            text=c.text,
                            similarity_score=c.similarity_score,
                            normalized_score=c.normalized_score,
                            rerank_score=c.rerank_score,
                            metadata={
                                **c.metadata,
                                "retrieval_source": f"q{q_idx}_sparse",
                                "query_text": q_str,
                            },
                            chunk_index=c.chunk_index,
                        )
                        for c in sparse_res
                    ]

            await asyncio.gather(do_dense(), do_sparse())
            return dense_res, sparse_res

        query_tasks = [fetch_for_query(q, i) for i, q in enumerate(final_query_set)]
        query_results = await asyncio.gather(*query_tasks)
        multi_retrieval_latency = time.perf_counter() - retrieval_ops_start

        for d_res, s_res in query_results:
            all_dense_results.append(d_res)
            all_sparse_results.append(s_res)

        # 4. Multi-Source Fusion & Canonical Deduplication
        fusion_start = time.perf_counter()
        multi_lists_weighted: list[tuple[list[RetrievedChunk], float]] = []

        for idx in range(len(final_query_set)):
            # Original query receives weight 1.0, derived queries inherit configured weights
            query_decay = 1.0 if idx == 0 else 0.85
            d_w = self._dense_weight * query_decay
            s_w = self._sparse_weight * query_decay

            if resolved_mode in (RetrievalMode.SEMANTIC, RetrievalMode.HYBRID):
                multi_lists_weighted.append((all_dense_results[idx], d_w))
            if resolved_mode in (RetrievalMode.SPARSE, RetrievalMode.HYBRID):
                multi_lists_weighted.append((all_sparse_results[idx], s_w))

        if self._enable_weighted_rrf:
            fused_candidates = self._weighted_fusion_engine.fuse_weighted(
                multi_lists_weighted
            )
        else:
            # Merge dense and sparse lists across queries, then apply standard RRF
            combined_dense: list[RetrievedChunk] = []
            combined_sparse: list[RetrievedChunk] = []
            for d_list in all_dense_results:
                combined_dense.extend(d_list)
            for s_list in all_sparse_results:
                combined_sparse.extend(s_list)

            # Deduplicate inputs preserving order for standard RRF
            dedup_dense = list({c.chunk_id: c for c in combined_dense}.values())
            dedup_sparse = list({c.chunk_id: c for c in combined_sparse}.values())
            fused_candidates = self._fusion_engine.fuse(dedup_dense, dedup_sparse)

        fusion_latency = time.perf_counter() - fusion_start

        # Cap total retrieval candidate pool
        bounded_candidates = fused_candidates[: self._max_retrieval_candidates]

        # 5. MMR Diversity Selection
        if self._enable_mmr:
            mmr_results = self._mmr_selector.select(
                chunks=bounded_candidates,
                top_k=top_k,
                mmr_lambda=self._mmr_lambda,
            )
        else:
            mmr_results = bounded_candidates[:top_k]

        # 6. Cross-Encoder Reranking (Using original user query)
        reranked_results = mmr_results
        rerank_latency = 0.0
        if self._enable_reranker:
            t0 = time.perf_counter()
            processed_orig = self._query_processor.process(query)
            if self._ranker:
                reranked_results = self._ranker.rank(
                    processed_orig.cleaned_query, mmr_results
                )
            else:
                reranked_results = await self._reranker.rerank(
                    processed_orig.cleaned_query, mmr_results
                )
            reranked_results = reranked_results[: self._rerank_top_k]
            rerank_latency = time.perf_counter() - t0

        total_latency = time.perf_counter() - start_time
        # Flatten dense/sparse matches for reporting
        flat_dense = [c for sub in all_dense_results for c in sub]
        flat_sparse = [c for sub in all_sparse_results for c in sub]

        try:
            from app.core.telemetry import (
                RETRIEVAL_CANDIDATES_COUNT,
                RETRIEVAL_REQUESTS,
                RETRIEVAL_STAGE_DURATION,
            )

            RETRIEVAL_REQUESTS.labels(mode=resolved_mode.value, status="success").inc()
            RETRIEVAL_STAGE_DURATION.labels(stage="dense").observe(
                multi_retrieval_latency
            )
            RETRIEVAL_STAGE_DURATION.labels(stage="fusion").observe(fusion_latency)
            RETRIEVAL_STAGE_DURATION.labels(stage="rerank").observe(rerank_latency)
            RETRIEVAL_CANDIDATES_COUNT.labels(stage="dense").observe(len(flat_dense))
            RETRIEVAL_CANDIDATES_COUNT.labels(stage="sparse").observe(len(flat_sparse))
            RETRIEVAL_CANDIDATES_COUNT.labels(stage="fused").observe(
                len(fused_candidates)
            )
            RETRIEVAL_CANDIDATES_COUNT.labels(stage="reranked").observe(
                len(reranked_results)
            )
        except Exception:
            pass

        diagnostics_data = {
            "query_type": classification.query_type.value,
            "classification_confidence": classification.confidence,
            "classification_latency_ms": classification_latency * 1000.0,
            "expansion_latency_ms": expansion_latency * 1000.0,
            "decomposition_latency_ms": decomposition_latency * 1000.0,
            "multi_retrieval_latency_ms": multi_retrieval_latency * 1000.0,
            "fusion_latency_ms": fusion_latency * 1000.0,
            "rerank_latency_ms": rerank_latency * 1000.0,
            "total_queries_executed": len(final_query_set),
            "retrieval_queries": final_query_set,
            "candidates_before_mmr": len(fused_candidates),
            "candidates_after_mmr": len(mmr_results),
            "final_candidates": len(reranked_results),
        }

        logger.info(
            f"Advanced Retrieval stats [mode: {resolved_mode.value}, type: {classification.query_type.value}] - "
            f"queries: {len(final_query_set)}, "
            f"dense_count: {len(flat_dense)}, "
            f"sparse_count: {len(flat_sparse)}, "
            f"fused: {len(fused_candidates)}, "
            f"reranked: {len(reranked_results)}, "
            f"total_latency: {total_latency:.4f}s"
        )

        return SearchResult(
            original_query=query,
            retrieval_time=total_latency,
            total_matches=len(reranked_results),
            retrieved_chunks=reranked_results,
            search_strategy=resolved_mode.value,
            retrieval_strategy=resolved_mode,
            dense_matches=flat_dense,
            sparse_matches=flat_sparse,
            fusion_method=FusionMethod.RRF,
            reranker=(
                RerankerName(type(self._reranker).__name__)
                if self._enable_reranker
                and type(self._reranker).__name__ in RerankerName._value2member_map_
                else None
            ),
            query_type=classification.query_type.value,
            expanded_queries=expanded_queries_list,
            subtask_queries=subtask_queries_list,
            diagnostics=diagnostics_data,
        )

    async def retrieve_with_hyde_dense(
        self,
        query: str,
        user_id: UUID,
        hyde_dense_chunks: list[RetrievedChunk],
        top_k: int = 10,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        retrieval_scope: DocumentRetrievalScope | None = None,
    ) -> SearchResult:
        """
        Canonical HyDE Hybrid Retrieval Pipeline:
        1. Validates and enforces document authorization and scope on all candidates before fusion.
        2. Tags hypothetical dense chunks with provenance: metadata["retrieval_source"] = "hyde_dense".
        3. Executes BM25 sparse retrieval using the ORIGINAL user query.
        4. Fuses HyDE dense chunks and BM25 sparse chunks using the canonical Weighted/Standard RRF engine.
        5. Applies MMR diversity selection (if enabled).
        6. Reranks candidates using the ORIGINAL user query via Cross-Encoder.
        7. Returns final SearchResult preserving provenance and metadata.
        """
        start_time = time.perf_counter()

        if self._chunk_repo is None:
            raise RuntimeError(
                "Chunk repository is not configured; cannot verify document ownership."
            )

        if retrieval_scope is None:
            retrieval_scope = DocumentRetrievalScope(
                user_id=user_id,
                conversation_id=None,
                include_conversation_documents=True,
                include_library_documents=True,
                document_ids=document_ids,
                tags=tags,
                filter_metadata=filter_metadata,
            )

        # 1. Resolve and verify allowed document IDs from repository
        allowed_doc_ids = await self._chunk_repo.get_allowed_document_ids(
            retrieval_scope
        )

        if retrieval_scope.document_ids:
            unauthorized = set(retrieval_scope.document_ids) - set(allowed_doc_ids)
            if unauthorized:
                raise UnauthorizedDocumentAccess(
                    "Unauthorized document access: one or more specified document IDs do not belong to you or are not in scope."
                )
            allowed_doc_ids = [
                doc_id
                for doc_id in allowed_doc_ids
                if doc_id in retrieval_scope.document_ids
            ]

        if not allowed_doc_ids:
            logger.info(
                "HyDE retrieval skipped: no documents match the requested scope."
            )
            return SearchResult(
                original_query=query,
                retrieval_time=time.perf_counter() - start_time,
                total_matches=0,
                retrieved_chunks=[],
                search_strategy="hyde",
                retrieval_strategy=RetrievalMode.HYBRID,
                dense_matches=[],
                sparse_matches=[],
            )

        # 2. Filter & Tag HyDE dense chunks with provenance BEFORE fusion
        allowed_doc_id_set = set(allowed_doc_ids)
        authorized_hyde_dense: list[RetrievedChunk] = []
        for c in hyde_dense_chunks:
            if c.document_id in allowed_doc_id_set:
                merged_meta = dict(c.metadata) if c.metadata else {}
                merged_meta["retrieval_source"] = "hyde_dense"
                authorized_hyde_dense.append(
                    RetrievedChunk(
                        chunk_id=c.chunk_id,
                        document_id=c.document_id,
                        document_name=c.document_name,
                        text=c.text,
                        similarity_score=c.similarity_score,
                        normalized_score=c.normalized_score,
                        rerank_score=c.rerank_score,
                        metadata=merged_meta,
                        chunk_index=c.chunk_index,
                    )
                )

        # 3. Sparse retrieval using original query
        processed_query_obj = self._query_processor.process(query)
        s_top_k = self._bm25_top_k or top_k
        sparse_results: list[RetrievedChunk] = []
        sparse_latency = 0.0

        if self._sparse_retriever:
            t0 = time.perf_counter()
            raw_sparse = await self._sparse_retriever.retrieve(
                query=processed_query_obj.expanded_query,
                user_id=user_id,
                top_k=s_top_k,
                document_ids=allowed_doc_ids,
                tags=tags,
                filter_metadata=filter_metadata,
                retrieval_scope=retrieval_scope,
            )
            sparse_latency = time.perf_counter() - t0
            for c in raw_sparse:
                if c.document_id in allowed_doc_id_set:
                    merged_meta = dict(c.metadata) if c.metadata else {}
                    merged_meta["retrieval_source"] = "bm25"
                    sparse_results.append(
                        RetrievedChunk(
                            chunk_id=c.chunk_id,
                            document_id=c.document_id,
                            document_name=c.document_name,
                            text=c.text,
                            similarity_score=c.similarity_score,
                            normalized_score=c.normalized_score,
                            rerank_score=c.rerank_score,
                            metadata=merged_meta,
                            chunk_index=c.chunk_index,
                        )
                    )

        # 4. Fusion Engine
        fusion_start = time.perf_counter()
        if self._enable_weighted_rrf:
            fused_results = self._weighted_fusion_engine.fuse_weighted(
                [
                    (authorized_hyde_dense, self._dense_weight),
                    (sparse_results, self._sparse_weight),
                ]
            )
        else:
            fused_results = self._fusion_engine.fuse(
                authorized_hyde_dense, sparse_results
            )
        fusion_latency = time.perf_counter() - fusion_start

        # 5. MMR Diversity Selection
        if self._enable_mmr:
            mmr_results = self._mmr_selector.select(
                chunks=fused_results,
                top_k=top_k,
                mmr_lambda=self._mmr_lambda,
            )
        else:
            mmr_results = fused_results[:top_k]

        # 6. Reranking (Using original user query!)
        reranked_results = mmr_results
        rerank_latency = 0.0
        if self._enable_reranker:
            t0 = time.perf_counter()
            if self._ranker:
                reranked_results = self._ranker.rank(
                    processed_query_obj.cleaned_query, mmr_results
                )
            else:
                reranked_results = await self._reranker.rerank(
                    processed_query_obj.cleaned_query, mmr_results
                )
            reranked_results = reranked_results[: self._rerank_top_k]
            rerank_latency = time.perf_counter() - t0

        total_latency = time.perf_counter() - start_time

        return SearchResult(
            original_query=query,
            retrieval_time=total_latency,
            total_matches=len(reranked_results),
            retrieved_chunks=reranked_results,
            search_strategy="hyde",
            retrieval_strategy=RetrievalMode.HYBRID,
            dense_matches=authorized_hyde_dense,
            sparse_matches=sparse_results,
            fusion_method=FusionMethod.RRF,
            reranker=(
                RerankerName(type(self._reranker).__name__)
                if self._enable_reranker
                and type(self._reranker).__name__ in RerankerName._value2member_map_
                else None
            ),
            diagnostics={
                "hyde_dense_count": len(authorized_hyde_dense),
                "sparse_count": len(sparse_results),
                "fused_count": len(fused_results),
                "final_count": len(reranked_results),
                "sparse_latency_ms": sparse_latency * 1000.0,
                "fusion_latency_ms": fusion_latency * 1000.0,
                "rerank_latency_ms": rerank_latency * 1000.0,
                "total_latency_ms": total_latency * 1000.0,
            },
        )
