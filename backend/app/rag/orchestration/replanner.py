import hashlib
import logging
from uuid import UUID, uuid4

from app.documents.domain.models import DocumentRetrievalScope
from app.rag.orchestration.models import (
    EvidenceAssessment,
    RetrievalDecision,
    RetrievalStrategy,
    RetrievalTask,
    RetrievalTaskResult,
    TaskStatus,
)

logger = logging.getLogger(__name__)


def compute_task_fingerprint(
    query: str, strategy: RetrievalStrategy, scope: DocumentRetrievalScope
) -> str:
    """Computes a deterministic hash fingerprint for a task to prevent duplicate executions."""
    normalized_q = " ".join(query.strip().lower().split())
    doc_ids_str = (
        ",".join(sorted(str(d) for d in scope.document_ids))
        if scope.document_ids
        else "all"
    )
    raw = f"{normalized_q}|{strategy.value}|{scope.user_id}|{scope.conversation_id}|{doc_ids_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class Replanner:
    """
    Replanning engine that analyzes evidence gaps and contradictions
    to generate targeted, non-redundant follow-up RetrievalTasks.
    """

    def __init__(self, max_tasks_per_replan: int = 3) -> None:
        self._max_tasks_per_replan = max_tasks_per_replan

    async def replan(
        self,
        original_query: str,
        decision: RetrievalDecision,
        assessment: EvidenceAssessment,
        completed_tasks: list[RetrievalTaskResult],
        scope: DocumentRetrievalScope,
        executed_fingerprints: set[str],
        parent_task_id: UUID | None = None,
    ) -> list[RetrievalTask]:
        """
        Generates targeted follow-up tasks for missing evidence targets or conflicting claims.
        Prevents duplicate tasks using task fingerprints.
        """
        if assessment.sufficient:
            return []

        new_tasks: list[RetrievalTask] = []

        # 1. Handle Contradictions: Spawn a targeted verification task
        if assessment.conflicting_evidence and assessment.conflict_details:
            for conflict_info in assessment.conflict_details:
                verify_query = f"Verify factual details and resolve conflict: {conflict_info} for query: {original_query}"
                fp = compute_task_fingerprint(
                    verify_query, RetrievalStrategy.STANDARD_HYBRID, scope
                )
                if fp not in executed_fingerprints:
                    executed_fingerprints.add(fp)
                    new_tasks.append(
                        RetrievalTask(
                            task_id=uuid4(),
                            parent_task_id=parent_task_id,
                            query=verify_query,
                            strategy=RetrievalStrategy.STANDARD_HYBRID,
                            required_evidence=[conflict_info],
                            scope=scope,
                            priority=1,
                            status=TaskStatus.PENDING,
                            fingerprint=fp,
                        )
                    )

        # 2. Handle Missing Targets: Spawn targeted retrieval for specific missing targets
        for missing_target in assessment.missing_targets:
            if len(new_tasks) >= self._max_tasks_per_replan:
                break

            targeted_query = missing_target.strip()
            if not targeted_query:
                continue

            # Formalized runtime transition strategy for iterative follow-up retrieval
            strategy = (
                RetrievalStrategy.QUERY_EXPANSION
                if len(targeted_query.split()) <= 2 and " " not in targeted_query
                else RetrievalStrategy.ITERATIVE
            )

            fp = compute_task_fingerprint(targeted_query, strategy, scope)
            if fp in executed_fingerprints:
                logger.info(
                    f"Replanner skipping duplicate task with fingerprint {fp}: '{targeted_query}'"
                )
                continue

            executed_fingerprints.add(fp)
            new_tasks.append(
                RetrievalTask(
                    task_id=uuid4(),
                    parent_task_id=parent_task_id,
                    query=targeted_query,
                    strategy=strategy,
                    required_evidence=[missing_target],
                    scope=scope,
                    priority=2,
                    status=TaskStatus.PENDING,
                    fingerprint=fp,
                )
            )

        logger.info(
            f"Replanner generated {len(new_tasks)} new targeted tasks for missing targets: {assessment.missing_targets}"
        )
        return new_tasks
