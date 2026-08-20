import asyncio
import logging
import time
from typing import Any
from uuid import UUID, uuid4

from app.core.config import settings
from app.documents.domain.interfaces import (
    ChunkRepository,
)
from app.documents.domain.models import (
    DocumentRetrievalScope,
    FusionMethod,
    RetrievalMode,
    RetrievedChunk,
    SearchResult,
)
from app.documents.services.hyde import SafeHyDEExecutor
from app.documents.services.query_classifier import (
    DeterministicQueryClassifier,
    QueryClassification,
    QueryClassifier,
)
from app.documents.services.query_decomposer import (
    DeterministicQueryDecomposer,
    QueryDecomposer,
)
from app.documents.services.retrieval_service import RetrievalService
from app.rag.orchestration.evidence_evaluator import EvidenceSufficiencyEvaluator
from app.rag.orchestration.models import (
    EvidenceAssessment,
    MultiAgentDiagnostics,
    OrchestrationStatus,
    RetrievalDecision,
    RetrievalStrategy,
    RetrievalTask,
    RetrievalTaskResult,
    TaskStatus,
)
from app.rag.orchestration.replanner import Replanner, compute_task_fingerprint
from app.rag.orchestration.strategy_router import RetrievalStrategyRouter
from app.rag.orchestration.telemetry import (
    OrchestrationTelemetry,
    OrchestrationTelemetryEvent,
)
from app.rag.orchestration.worker import RetrievalWorker

logger = logging.getLogger(__name__)


class AdaptiveRAGOrchestrator:
    """
    Master Orchestrator for Adaptive / Agentic RAG.

    Coordinates:
    1. Strategy routing & query classification.
    2. Master-worker retrieval dispatch.
    3. Evidence aggregation and sufficiency assessment.
    4. Targeted replanning for missing evidence & conflict verification.
    5. Strict termination budgets (iterations, tasks, retrieval calls, timeouts).
    6. Minimum sufficient retrieval optimization.
    """

    def __init__(
        self,
        retrieval_service: RetrievalService,
        strategy_router: RetrievalStrategyRouter | None = None,
        evidence_evaluator: EvidenceSufficiencyEvaluator | None = None,
        replanner: Replanner | None = None,
        query_classifier: QueryClassifier | None = None,
        query_decomposer: QueryDecomposer | None = None,
        hyde_executor: SafeHyDEExecutor | None = None,
        telemetry: OrchestrationTelemetry | None = None,
        chunk_repo: ChunkRepository | None = None,
        # Configurable resource budgets
        max_iterations: int | None = None,
        max_tasks: int | None = None,
        max_retrieval_calls: int | None = None,
        max_replans: int | None = None,
        total_timeout_ms: int | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._query_classifier = query_classifier or DeterministicQueryClassifier()
        self._strategy_router = strategy_router or RetrievalStrategyRouter(
            self._query_classifier
        )
        self._evidence_evaluator = evidence_evaluator or EvidenceSufficiencyEvaluator(
            min_relevance_threshold=getattr(settings, "SIMILARITY_THRESHOLD", 0.25)
        )
        self._replanner = replanner or Replanner()
        self._query_decomposer = query_decomposer or DeterministicQueryDecomposer()
        self._hyde_executor = hyde_executor
        self._telemetry = telemetry or OrchestrationTelemetry()
        self._chunk_repo = chunk_repo

        # Budgets
        self._max_iterations = (
            max_iterations
            if max_iterations is not None
            else getattr(settings, "MAX_AGENT_ITERATIONS", 3)
        )
        self._max_tasks = (
            max_tasks
            if max_tasks is not None
            else getattr(settings, "MAX_AGENT_TASKS", 8)
        )
        self._max_retrieval_calls = (
            max_retrieval_calls
            if max_retrieval_calls is not None
            else getattr(settings, "MAX_AGENT_RETRIEVAL_CALLS", 12)
        )
        self._max_replans = (
            max_replans
            if max_replans is not None
            else getattr(settings, "MAX_AGENT_REPLANS", 2)
        )
        self._total_timeout_sec = (
            (total_timeout_ms / 1000.0)
            if total_timeout_ms is not None
            else (getattr(settings, "AGENT_TOTAL_TIMEOUT_MS", 5000) / 1000.0)
        )

        self._worker = RetrievalWorker(
            retrieval_service=self._retrieval_service,
            hyde_executor=self._hyde_executor,
        )

    async def retrieve(
        self,
        query: str,
        user_id: UUID,
        top_k: int = 10,
        conversation_id: UUID | None = None,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        retrieval_mode: Any | None = None,
        retrieval_scope: DocumentRetrievalScope | None = None,
    ) -> SearchResult:
        """Interface-compatible wrapper allowing drop-in retrieval invocation."""
        return await self.orchestrate(
            query=query,
            user_id=user_id,
            top_k=top_k,
            conversation_id=conversation_id,
            document_ids=document_ids,
            tags=tags,
            filter_metadata=filter_metadata,
            retrieval_scope=retrieval_scope,
        )

    async def orchestrate(
        self,
        query: str,
        user_id: UUID,
        top_k: int = 10,
        conversation_id: UUID | None = None,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        retrieval_scope: DocumentRetrievalScope | None = None,
    ) -> SearchResult:
        """
        Executes bounded master-worker adaptive RAG retrieval.
        """
        start_time = time.perf_counter()
        orchestration_id = uuid4()
        cleaned_query = query.strip()

        # 1. Resolve Document Retrieval Scope
        if retrieval_scope is None:
            retrieval_scope = DocumentRetrievalScope(
                user_id=user_id,
                conversation_id=conversation_id,
                include_conversation_documents=True,
                include_library_documents=True,
                document_ids=document_ids,
                tags=tags,
                filter_metadata=filter_metadata,
            )

        # 2. Query Classification & Strategy Routing
        classification: QueryClassification = self._query_classifier.classify(
            cleaned_query
        )
        decision: RetrievalDecision = await self._strategy_router.select_strategy(
            query=cleaned_query,
            classification=classification,
        )

        logger.info(
            f"AdaptiveRAG Master [{orchestration_id}] selected strategy '{decision.strategy.value}' "
            f"with confidence {decision.confidence:.2f}, signals: {decision.reasoning_signals}"
        )

        # 3. Create Initial Worker Tasks
        initial_tasks = await self._create_initial_tasks(
            query=cleaned_query,
            decision=decision,
            classification=classification,
            scope=retrieval_scope,
        )

        all_completed_tasks: list[RetrievalTaskResult] = []
        executed_fingerprints: set[str] = {
            t.fingerprint for t in initial_tasks if t.fingerprint
        }
        total_retrieval_calls = 0
        replan_count = 0
        duplicate_tasks_avoided = 0
        hyde_used = decision.strategy == RetrievalStrategy.HYDE
        expansion_used = decision.strategy == RetrievalStrategy.QUERY_EXPANSION
        decomposition_used = decision.strategy in (
            RetrievalStrategy.DECOMPOSITION,
            RetrievalStrategy.HYBRID_ADAPTIVE,
        )

        current_tasks_to_execute = list(initial_tasks)
        evidence_pool: list[RetrievedChunk] = []
        assessment: EvidenceAssessment | None = None
        final_status = OrchestrationStatus.SUCCESS

        # 4. Master Orchestration Loop (Bounded Iterations)
        iteration = 0
        while iteration < self._max_iterations:
            iteration += 1

            # Check Global Time Budget
            elapsed = time.perf_counter() - start_time
            if elapsed > self._total_timeout_sec:
                logger.warning(
                    f"AdaptiveRAG Master [{orchestration_id}] exceeded total timeout ({self._total_timeout_sec:.2f}s). Terminating."
                )
                final_status = OrchestrationStatus.TIMEOUT
                break

            # Check Global Task Budget
            if (
                len(all_completed_tasks) + len(current_tasks_to_execute)
                > self._max_tasks
            ):
                logger.warning(
                    f"AdaptiveRAG Master [{orchestration_id}] reached max tasks budget ({self._max_tasks})."
                )
                current_tasks_to_execute = current_tasks_to_execute[
                    : max(0, self._max_tasks - len(all_completed_tasks))
                ]
                final_status = OrchestrationStatus.BUDGET_EXCEEDED

            if not current_tasks_to_execute:
                break

            # Dispatch Workers Concurrently for current batch of tasks
            worker_futures = [self._worker.execute(t) for t in current_tasks_to_execute]
            batch_results: list[RetrievalTaskResult] = await asyncio.gather(
                *worker_futures
            )

            for res in batch_results:
                all_completed_tasks.append(res)
                total_retrieval_calls += res.retrieval_calls
                evidence_pool.extend(res.evidence)

            # Deduplicate Evidence Pool (Preserving Order)
            seen_cids = set()
            dedup_evidence: list[RetrievedChunk] = []
            for c in evidence_pool:
                cid_str = str(c.chunk_id)
                if cid_str not in seen_cids:
                    seen_cids.add(cid_str)
                    dedup_evidence.append(c)
            evidence_pool = dedup_evidence

            # 5. Evaluate Evidence Sufficiency
            assessment = await self._evidence_evaluator.evaluate(
                query=cleaned_query,
                evidence=evidence_pool,
                expected_targets=decision.expected_evidence_targets,
                scope=retrieval_scope,
                allowed_doc_ids=retrieval_scope.document_ids,
            )

            # Check Termination Condition (Minimum Sufficient Retrieval)
            if assessment.sufficient:
                logger.info(
                    f"AdaptiveRAG Master [{orchestration_id}] achieved sufficient evidence at iteration {iteration}. Terminating."
                )
                final_status = OrchestrationStatus.SUCCESS
                break

            # Check Retrieval Call Budget
            if total_retrieval_calls >= self._max_retrieval_calls:
                logger.info(
                    f"AdaptiveRAG Master [{orchestration_id}] reached retrieval call budget ({self._max_retrieval_calls}). Terminating with partial evidence."
                )
                final_status = OrchestrationStatus.PARTIAL
                break

            # Check Replan Budget
            if replan_count >= self._max_replans:
                logger.info(
                    f"AdaptiveRAG Master [{orchestration_id}] reached max replans ({self._max_replans}). Terminating."
                )
                final_status = OrchestrationStatus.PARTIAL
                break

            # 6. Trigger Replanner for Missing Evidence or Conflicts
            replan_count += 1
            new_tasks = await self._replanner.replan(
                original_query=cleaned_query,
                decision=decision,
                assessment=assessment,
                completed_tasks=all_completed_tasks,
                scope=retrieval_scope,
                executed_fingerprints=executed_fingerprints,
            )
            duplicate_tasks_avoided += max(
                0, len(assessment.missing_targets) - len(new_tasks)
            )
            current_tasks_to_execute = new_tasks

            if not current_tasks_to_execute:
                logger.info(
                    f"AdaptiveRAG Master [{orchestration_id}] replanner found no new distinct tasks. Terminating."
                )
                final_status = OrchestrationStatus.PARTIAL
                break

        total_latency = time.perf_counter() - start_time
        total_latency_ms = total_latency * 1000.0

        # Build Sanitized Diagnostics
        diagnostics_obj = MultiAgentDiagnostics(
            orchestration_id=orchestration_id,
            strategy=decision.strategy,
            strategy_confidence=decision.confidence,
            reasoning_signals=decision.reasoning_signals,
            tasks=[
                {
                    "task_id": str(t.task_id),
                    "parent_task_id": str(t.parent_task_id)
                    if t.parent_task_id
                    else None,
                    "strategy": t.strategy.value,
                    "evidence_count": t.evidence_count,
                    "retrieval_calls": t.retrieval_calls,
                    "latency_ms": t.latency_ms,
                    "status": t.status.value,
                }
                for t in all_completed_tasks
            ],
            iterations=iteration,
            evidence_assessment=assessment,
            retrieval_calls=total_retrieval_calls,
            latency_ms=total_latency_ms,
            replan_count=replan_count,
            duplicate_tasks_avoided=duplicate_tasks_avoided,
            conflict_detected=assessment.conflicting_evidence if assessment else False,
            conflict_resolved=(
                assessment.conflicting_evidence is False if assessment else True
            ),
            final_status=final_status,
        )

        # Record Telemetry
        self._telemetry.record(
            OrchestrationTelemetryEvent(
                orchestration_id=orchestration_id,
                query_type=classification.query_type.value,
                selected_strategy=decision.strategy.value,
                strategy_confidence=decision.confidence,
                task_count=len(all_completed_tasks),
                completed_task_count=sum(
                    1 for t in all_completed_tasks if t.status == TaskStatus.COMPLETED
                ),
                failed_task_count=sum(
                    1 for t in all_completed_tasks if t.status == TaskStatus.FAILED
                ),
                replan_count=replan_count,
                retrieval_call_count=total_retrieval_calls,
                hyde_used=hyde_used,
                hyde_latency_ms=0.0,
                expansion_used=expansion_used,
                decomposition_used=decomposition_used,
                evidence_sufficiency_score=assessment.confidence if assessment else 0.0,
                missing_evidence_count=len(assessment.missing_targets)
                if assessment
                else 0,
                duplicate_task_count=duplicate_tasks_avoided,
                conflict_detected=assessment.conflicting_evidence
                if assessment
                else False,
                conflict_resolved=(
                    assessment.conflicting_evidence is False if assessment else True
                ),
                final_status=final_status.value,
                total_latency_ms=total_latency_ms,
            )
        )

        # Return Combined SearchResult
        return SearchResult(
            original_query=cleaned_query,
            retrieval_time=total_latency,
            total_matches=len(evidence_pool),
            retrieved_chunks=evidence_pool[:top_k],
            search_strategy=decision.strategy.value,
            retrieval_strategy=RetrievalMode.HYBRID,
            dense_matches=[
                c
                for c in evidence_pool
                if "dense" in str(c.metadata.get("retrieval_source", ""))
            ],
            sparse_matches=[
                c
                for c in evidence_pool
                if "sparse" in str(c.metadata.get("retrieval_source", ""))
            ],
            fusion_method=FusionMethod.RRF,
            query_type=classification.query_type.value,
            diagnostics={
                **diagnostics_obj.model_dump(),
                "orchestration_id": str(orchestration_id),
                "strategy": decision.strategy.value,
                "strategy_confidence": decision.confidence,
                "reasoning_signals": decision.reasoning_signals,
                "total_tasks_executed": len(all_completed_tasks),
                "total_retrieval_calls": total_retrieval_calls,
                "iterations": iteration,
                "replan_count": replan_count,
                "final_status": final_status.value,
                "evidence_sufficiency": assessment.sufficient if assessment else False,
                "missing_targets": assessment.missing_targets if assessment else [],
                "supported_targets": assessment.supported_targets if assessment else [],
                "conflicting_evidence": assessment.conflicting_evidence
                if assessment
                else False,
            },
        )

    async def _create_initial_tasks(
        self,
        query: str,
        decision: RetrievalDecision,
        classification: QueryClassification,
        scope: DocumentRetrievalScope,
    ) -> list[RetrievalTask]:
        """Builds the initial set of worker tasks based on the selected strategy."""
        tasks: list[RetrievalTask] = []

        if decision.strategy in (
            RetrievalStrategy.DECOMPOSITION,
            RetrievalStrategy.HYBRID_ADAPTIVE,
        ):
            # Decompose query into subtasks
            subtasks = await self._query_decomposer.decompose(
                query, classification.query_type
            )
            for st in subtasks:
                sub_q = st.query.strip()
                fp = compute_task_fingerprint(
                    sub_q, RetrievalStrategy.STANDARD_HYBRID, scope
                )
                tasks.append(
                    RetrievalTask(
                        task_id=uuid4(),
                        query=sub_q,
                        strategy=RetrievalStrategy.STANDARD_HYBRID,
                        required_evidence=[sub_q],
                        scope=scope,
                        priority=1,
                        fingerprint=fp,
                    )
                )

            # If decomposition yielded only one subtask or empty, add original query
            if not tasks:
                fp = compute_task_fingerprint(
                    query, RetrievalStrategy.STANDARD_HYBRID, scope
                )
                tasks.append(
                    RetrievalTask(
                        task_id=uuid4(),
                        query=query,
                        strategy=RetrievalStrategy.STANDARD_HYBRID,
                        required_evidence=decision.expected_evidence_targets,
                        scope=scope,
                        priority=1,
                        fingerprint=fp,
                    )
                )

        elif decision.strategy == RetrievalStrategy.HYDE:
            fp = compute_task_fingerprint(query, RetrievalStrategy.HYDE, scope)
            tasks.append(
                RetrievalTask(
                    task_id=uuid4(),
                    query=query,
                    strategy=RetrievalStrategy.HYDE,
                    required_evidence=decision.expected_evidence_targets,
                    scope=scope,
                    priority=1,
                    fingerprint=fp,
                )
            )

        elif decision.strategy == RetrievalStrategy.QUERY_EXPANSION:
            fp = compute_task_fingerprint(
                query, RetrievalStrategy.QUERY_EXPANSION, scope
            )
            tasks.append(
                RetrievalTask(
                    task_id=uuid4(),
                    query=query,
                    strategy=RetrievalStrategy.QUERY_EXPANSION,
                    required_evidence=decision.expected_evidence_targets,
                    scope=scope,
                    priority=1,
                    fingerprint=fp,
                )
            )

        else:  # STANDARD_HYBRID
            fp = compute_task_fingerprint(
                query, RetrievalStrategy.STANDARD_HYBRID, scope
            )
            tasks.append(
                RetrievalTask(
                    task_id=uuid4(),
                    query=query,
                    strategy=RetrievalStrategy.STANDARD_HYBRID,
                    required_evidence=decision.expected_evidence_targets,
                    scope=scope,
                    priority=1,
                    fingerprint=fp,
                )
            )

        return tasks
