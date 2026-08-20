from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.documents.domain.models import (
    DocumentRetrievalScope,
    RetrievedChunk,
    SearchResult,
)


class RetrievalStrategy(str, Enum):
    """
    Retrieval strategy determined by the Adaptive Strategy Router.
    """

    STANDARD_HYBRID = "standard_hybrid"
    QUERY_EXPANSION = "query_expansion"
    HYDE = "hyde"
    DECOMPOSITION = "decomposition"
    ITERATIVE = "iterative"
    HYBRID_ADAPTIVE = "hybrid_adaptive"


class TaskStatus(str, Enum):
    """Execution status for worker retrieval tasks."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class OrchestrationStatus(str, Enum):
    """Final outcome status of the adaptive master orchestration."""

    SUCCESS = "success"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"


class RetrievalDecision(BaseModel):
    """
    Observable routing decision produced by the RetrievalStrategyRouter.
    Contains structured reasoning signals and evidence targets without chain-of-thought.
    """

    strategy: RetrievalStrategy
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_signals: list[str] = Field(default_factory=list)
    expected_evidence_targets: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=1, ge=1)
    max_retrieval_calls: int = Field(default=1, ge=1)

    model_config = ConfigDict(frozen=True)


class RetrievalTask(BaseModel):
    """
    A discrete retrieval unit executed by a RetrievalWorker.
    Inherits and preserves document scope and user authorization strictly.
    """

    task_id: UUID = Field(default_factory=uuid4)
    parent_task_id: UUID | None = None
    query: str
    strategy: RetrievalStrategy
    required_evidence: list[str] = Field(default_factory=list)
    scope: DocumentRetrievalScope
    priority: int = 1
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    fingerprint: str = ""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class RetrievalTaskResult(BaseModel):
    """
    Observable output from a RetrievalWorker execution.
    """

    task_id: UUID
    parent_task_id: UUID | None = None
    strategy: RetrievalStrategy
    evidence: list[RetrievedChunk] = Field(default_factory=list)
    search_result: SearchResult | None = None
    start_time: float = 0.0
    end_time: float = 0.0
    latency_ms: float = 0.0
    retrieval_calls: int = 1
    evidence_count: int = 0
    failure_reason: str | None = None
    status: TaskStatus = TaskStatus.COMPLETED

    model_config = ConfigDict(arbitrary_types_allowed=True)


class EvidenceAssessment(BaseModel):
    """
    Outcome of evidence sufficiency and contradiction evaluation.
    Evaluated strictly against observable evidence chunks.
    """

    sufficient: bool
    confidence: float = Field(ge=0.0, le=1.0)
    missing_targets: list[str] = Field(default_factory=list)
    supported_targets: list[str] = Field(default_factory=list)
    conflicting_evidence: bool = False
    duplicate_evidence: bool = False
    citation_ready: bool = True
    conflict_details: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class MultiAgentDiagnostics(BaseModel):
    """
    Sanitized observability and diagnostic summary for an orchestration session.
    Never contains raw document contents, private credentials, or chain-of-thought.
    """

    orchestration_id: UUID
    strategy: RetrievalStrategy
    strategy_confidence: float = 1.0
    reasoning_signals: list[str] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    iterations: int = 1
    evidence_assessment: EvidenceAssessment | None = None
    retrieval_calls: int = 1
    latency_ms: float = 0.0
    replan_count: int = 0
    duplicate_tasks_avoided: int = 0
    conflict_detected: bool = False
    conflict_resolved: bool = False
    final_status: OrchestrationStatus = OrchestrationStatus.SUCCESS

    model_config = ConfigDict(arbitrary_types_allowed=True)
