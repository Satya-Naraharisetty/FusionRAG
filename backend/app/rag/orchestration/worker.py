import logging
import time

from app.documents.domain.models import (
    RetrievalMode,
    SearchResult,
)
from app.documents.services.hyde import SafeHyDEExecutor
from app.documents.services.retrieval_service import RetrievalService
from app.rag.orchestration.models import (
    RetrievalStrategy,
    RetrievalTask,
    RetrievalTaskResult,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class RetrievalWorker:
    """
    Dedicated worker executing a single assigned RetrievalTask.
    Enforces strict scope inheritance (user_id, conversation_id, allowed_document_ids).

    CRITICAL INVARIANT:
    Workers MUST NOT instantiate or invoke AdaptiveRAGOrchestrator.
    Workers execute assigned tasks via RetrievalService / SafeHyDEExecutor only.
    """

    def __init__(
        self,
        retrieval_service: RetrievalService,
        hyde_executor: SafeHyDEExecutor | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._hyde_executor = hyde_executor

    async def execute(self, task: RetrievalTask) -> RetrievalTaskResult:
        start_time = time.perf_counter()
        query = task.query.strip()
        scope = task.scope

        retrieval_calls = 1
        evidence_chunks = []
        search_res: SearchResult | None = None

        try:
            if (
                task.strategy == RetrievalStrategy.HYDE
                and self._hyde_executor is not None
            ):
                # HyDE execution: dense search via hypothetical embedding, BM25 via original query
                top_k = getattr(self._retrieval_service, "_vector_top_k", 10)
                (
                    dense_chunks,
                    hypo_doc,
                    hyde_latency,
                ) = await self._hyde_executor.execute_hyde_dense_retrieval(
                    query=query,
                    user_id=scope.user_id,
                    top_k=top_k,
                    document_ids=scope.document_ids,
                    tags=scope.tags,
                    filter_metadata=scope.filter_metadata,
                    retrieval_scope=scope,
                )

                # Delegate to canonical pipeline for fusion with BM25 original query, MMR, and cross-encoder
                search_res = await self._retrieval_service.retrieve_with_hyde_dense(
                    query=query,
                    user_id=scope.user_id,
                    hyde_dense_chunks=dense_chunks,
                    top_k=top_k,
                    document_ids=scope.document_ids,
                    tags=scope.tags,
                    filter_metadata=scope.filter_metadata,
                    retrieval_scope=scope,
                )
                evidence_chunks = search_res.retrieved_chunks
                retrieval_calls = 1

            elif task.strategy == RetrievalStrategy.QUERY_EXPANSION:
                # Execute retrieval with expansion enabled
                top_k = getattr(self._retrieval_service, "_default_top_k", 10)
                search_res = await self._retrieval_service.retrieve(
                    query=query,
                    user_id=scope.user_id,
                    top_k=top_k,
                    document_ids=scope.document_ids,
                    tags=scope.tags,
                    filter_metadata=scope.filter_metadata,
                    retrieval_mode=RetrievalMode.HYBRID,
                    retrieval_scope=scope,
                )
                evidence_chunks = search_res.retrieved_chunks
                retrieval_calls = (
                    search_res.diagnostics.get("total_queries_executed", 1)
                    if search_res.diagnostics
                    else 1
                )

            else:
                # Standard Hybrid / Targeted / Subtask retrieval
                top_k = getattr(self._retrieval_service, "_default_top_k", 10)
                search_res = await self._retrieval_service.retrieve(
                    query=query,
                    user_id=scope.user_id,
                    top_k=top_k,
                    document_ids=scope.document_ids,
                    tags=scope.tags,
                    filter_metadata=scope.filter_metadata,
                    retrieval_mode=RetrievalMode.HYBRID,
                    retrieval_scope=scope,
                )
                evidence_chunks = search_res.retrieved_chunks
                retrieval_calls = 1

            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000.0

            return RetrievalTaskResult(
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                strategy=task.strategy,
                evidence=evidence_chunks,
                search_result=search_res,
                start_time=start_time,
                end_time=end_time,
                latency_ms=latency_ms,
                retrieval_calls=retrieval_calls,
                evidence_count=len(evidence_chunks),
                failure_reason=None,
                status=TaskStatus.COMPLETED,
            )

        except Exception as e:
            logger.error(
                f"RetrievalWorker task {task.task_id} failed: {e}", exc_info=True
            )
            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000.0
            return RetrievalTaskResult(
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                strategy=task.strategy,
                evidence=[],
                search_result=None,
                start_time=start_time,
                end_time=end_time,
                latency_ms=latency_ms,
                retrieval_calls=retrieval_calls,
                evidence_count=0,
                failure_reason=str(e),
                status=TaskStatus.FAILED,
            )
