from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.chat.domain.models import Citation, Usage
from app.documents.domain.models import DocumentRetrievalScope


class CapabilityType(str, Enum):
    RESEARCH = "RESEARCH"
    DOCUMENT_INSPECTION = "DOCUMENT_INSPECTION"
    ANALYSIS = "ANALYSIS"
    WEB_SEARCH = "WEB_SEARCH"
    SYNTHESIS = "SYNTHESIS"
    TABLE = "TABLE"
    VISION = "VISION"
    GRAPH = "GRAPH"


MAX_REPLAN_ATTEMPTS: int = 2
MAX_PLAN_ATTEMPTS: int = 3
MAX_TOTAL_CAPABILITY_CALLS_PER_PLAN: int = 15


class CapabilityDescriptor(BaseModel):
    capability_id: str
    capability_type: CapabilityType
    description: str
    supported_operations: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    estimated_latency_ms: float = 0.0
    estimated_cost_units: float = 0.0
    max_concurrency: int | None = None
    max_calls_per_plan: int = 5
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityRequirement(BaseModel):
    capability_type: CapabilityType | None = None
    operation: str = ""
    required_context: list[str] = Field(default_factory=list)
    preferred: bool = False
    priority: int = 0


class RoutingDecision(BaseModel):
    task_id: str
    selected_capability_id: str | None = None
    capability_type: CapabilityType | None = None
    eligible_capabilities: list[str] = Field(default_factory=list)
    rejected_capabilities: dict[str, str] = Field(default_factory=dict)
    reason_code: str = "EXACT_CAPABILITY_MATCH"
    confidence: float = 1.0
    estimated_latency_ms: float = 0.0
    estimated_cost_units: float = 0.0


class RoutingDiagnostics(BaseModel):
    routing_decisions: int = 0
    capability_rejections: int = 0
    fallback_routes: int = 0
    unavailable_capabilities: int = 0
    routing_latency_ms: float = 0.0
    estimated_cost_units: float = 0.0
    estimated_latency_ms: float = 0.0


class AgentType(str, Enum):
    MASTER = "MASTER"
    RESEARCH = "RESEARCH"
    DOCUMENT = "DOCUMENT"
    ANALYSIS = "ANALYSIS"
    WEB_SEARCH = "WEB_SEARCH"
    SYNTHESIS = "SYNTHESIS"
    TABLE = "TABLE"
    VISION = "VISION"
    GRAPH = "GRAPH"


class AgentTaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class AgentFailureReason(str, Enum):
    TIMEOUT = "TIMEOUT"
    DEPENDENCY_FAILED = "DEPENDENCY_FAILED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    UNAUTHORIZED = "UNAUTHORIZED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"


class EvaluationDecision(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    PARTIAL = "PARTIAL"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


class EvidenceItem(BaseModel):
    chunk_id: UUID | None = None
    document_id: UUID | None = None
    document_name: str
    content: str
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    task_id: str
    request: str
    agent_type: AgentType
    dependencies: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    expected_outputs: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    is_required: bool = True
    retryable: bool = True
    capability_requirements: list[CapabilityRequirement] = Field(default_factory=list)
    preferred_capability: str | None = None
    max_latency_ms: float | None = None
    max_cost_units: float | None = None


class AgentResult(BaseModel):
    task_id: str
    agent_type: AgentType
    status: AgentTaskStatus
    success: bool
    output: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    failure_reason: AgentFailureReason | None = None
    execution_time_ms: float = 0.0


class MissingRequirement(BaseModel):
    requirement: str
    reason: str
    suggested_agent_type: AgentType | None = None
    priority: int = 0


class ResultEvaluation(BaseModel):
    decision: EvaluationDecision
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_count: int = 0
    successful_tasks: list[str] = Field(default_factory=list)
    failed_tasks: list[str] = Field(default_factory=list)
    missing_requirements: list[MissingRequirement] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    should_replan: bool = False
    reason: str = ""


class AgentExecutionContext(BaseModel):
    request_id: str
    user_id: UUID
    conversation_id: UUID | None = None
    include_library_documents: bool = False
    include_conversation_documents: bool = True
    document_ids: list[UUID] | None = None
    dependency_results: dict[str, AgentResult] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    request_id: str
    tasks: list[AgentTask]
    reasoning_summary: str | None = None
    iteration: int = 1


class ExecutionOutcome(BaseModel):
    request_id: str
    completed_results: list[AgentResult] = Field(default_factory=list)
    failed_results: list[AgentResult] = Field(default_factory=list)
    skipped_results: list[AgentResult] = Field(default_factory=list)
    total_calls: int = 0
    limits_reached: list[str] = Field(default_factory=list)
    execution_time_ms: float = 0.0


class SynthesisRequest(BaseModel):
    request_id: str
    original_request: str
    specialist_results: list[AgentResult]
    context: AgentExecutionContext


# ==========================================
# Research Planner Domain Models (Prompt 3.3)
# ==========================================


class ResearchQuery(BaseModel):
    query_id: str = Field(..., max_length=100)
    query: str = Field(..., max_length=300)
    purpose: str = Field(default="", max_length=300)
    priority: int = 0
    required_evidence: list[str] = Field(default_factory=list, max_length=10)
    dependencies: list[str] = Field(default_factory=list, max_length=5)
    retrieval_scope: DocumentRetrievalScope | None = None
    max_results: int = 5
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchPlan(BaseModel):
    request_id: str
    original_query: str
    queries: list[ResearchQuery] = Field(default_factory=list, max_length=10)
    reasoning_summary: str | None = Field(default=None, max_length=500)
    decomposition_strategy: str = "single_query"
    estimated_retrieval_calls: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchEvidenceSet(BaseModel):
    evidence: list[EvidenceItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    source_queries: dict[str, list[str]] = Field(default_factory=dict)
    deduplicated_count: int = 0
    total_candidates: int = 0
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchQueryContext(BaseModel):
    task_id: str
    user_id: UUID
    retrieval_scope: DocumentRetrievalScope
    dependency_evidence: dict[str, list[EvidenceItem]] = Field(default_factory=dict)


class MultiAgentDiagnostics(BaseModel):
    plan_iterations: int = 1
    total_specialist_calls: int = 0
    concurrency_savings_ms: float = 0.0
    task_latencies: dict[str, float] = Field(default_factory=dict)
    failed_tasks: list[str] = Field(default_factory=list)
    limits_reached: list[str] = Field(default_factory=list)
    evaluation_count: int = 0
    replans: int = 0
    initial_task_count: int = 0
    final_task_count: int = 0
    avoided_duplicate_tasks: int = 0
    retry_count: int = 0
    evaluation_latency_ms: float = 0.0
    planning_latency_ms: float = 0.0
    execution_latency_ms: float = 0.0
    synthesis_latency_ms: float = 0.0
    # Research Planner diagnostics (Prompt 3.3)
    research_plans_created: int = 0
    research_subqueries_generated: int = 0
    research_subqueries_executed: int = 0
    research_retrieval_calls: int = 0
    research_empty_queries: int = 0
    research_duplicate_evidence_removed: int = 0
    research_evidence_count: int = 0
    research_planning_latency_ms: float = 0.0
    research_retrieval_latency_ms: float = 0.0
    research_total_latency_ms: float = 0.0
    # Routing Diagnostics (Prompt 3.4)
    routing_decisions: int = 0
    capability_rejections: int = 0
    fallback_routes: int = 0
    unavailable_capabilities: int = 0
    routing_latency_ms: float = 0.0
    estimated_cost_units: float = 0.0
    estimated_latency_ms: float = 0.0


class MultiAgentResponse(BaseModel):
    answer: str
    plan: ExecutionPlan
    specialist_results: list[AgentResult]
    citations: list[Citation] = Field(default_factory=list)
    usage: Usage
    total_time_ms: float
    diagnostics: MultiAgentDiagnostics


# ==========================================
# Canonical Sanitized Diagnostics Models (P0)
# ==========================================


class SanitizedAgentTaskDiagnostic(BaseModel):
    task_id: str
    agent_type: str
    dependencies: list[str] = Field(default_factory=list)
    status: str
    success: bool
    execution_time_ms: float = 0.0
    routed_capability: str | None = None
    failure_reason: str | None = None
    error: str | None = None


class SanitizedAgentEvaluationDiagnostic(BaseModel):
    decision: str
    confidence: float = 1.0
    replan_count: int = 0
    should_replan: bool = False
    missing_requirements_count: int = 0
    contradictions_count: int = 0


class SanitizedAgentDiagnostics(BaseModel):
    multi_agent_execution: bool = True
    plan_reasoning: str | None = None
    plan_iterations: int = 1
    total_specialist_calls: int = 0
    total_time_ms: float = 0.0
    tasks: list[SanitizedAgentTaskDiagnostic] = Field(default_factory=list)
    evaluation: SanitizedAgentEvaluationDiagnostic | None = None
    concurrency_savings_ms: float = 0.0
    limits_reached: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    citation_count: int = 0
    avoided_duplicate_tasks: int = 0
    latencies: dict[str, float] = Field(default_factory=dict)


def format_sanitized_agent_diagnostics(
    diagnostics: MultiAgentDiagnostics | None = None,
    plan: ExecutionPlan | None = None,
    specialist_results: list[AgentResult] | None = None,
    total_time_ms: float = 0.0,
    citation_count: int = 0,
    latest_evaluation: ResultEvaluation | None = None,
) -> dict[str, Any]:
    """
    Constructs a bounded, JSON-serializable canonical diagnostic payload for multi-agent execution.
    Strictly excludes CoT, hidden thoughts, prompts, auth tokens, and raw document contents.
    """
    tasks_sanitized: list[dict[str, Any]] = []
    plan_tasks_map = {t.task_id: t for t in plan.tasks} if plan else {}

    results = specialist_results or []
    for r in results:
        t_plan = plan_tasks_map.get(r.task_id)
        routed_cap = r.metadata.get("routed_capability") if r.metadata else None
        safe_err = str(r.error)[:200] if r.error else None
        tasks_sanitized.append(
            SanitizedAgentTaskDiagnostic(
                task_id=str(r.task_id),
                agent_type=r.agent_type.value
                if hasattr(r.agent_type, "value")
                else str(r.agent_type),
                dependencies=list(t_plan.dependencies) if t_plan else [],
                status=r.status.value if hasattr(r.status, "value") else str(r.status),
                success=bool(r.success),
                execution_time_ms=round(float(r.execution_time_ms), 2),
                routed_capability=str(routed_cap) if routed_cap else None,
                failure_reason=r.failure_reason.value
                if hasattr(r.failure_reason, "value") and r.failure_reason
                else (str(r.failure_reason) if r.failure_reason else None),
                error=safe_err,
            ).model_dump()
        )

    eval_diag: dict[str, Any] | None = None
    if latest_evaluation:
        eval_diag = SanitizedAgentEvaluationDiagnostic(
            decision=latest_evaluation.decision.value
            if hasattr(latest_evaluation.decision, "value")
            else str(latest_evaluation.decision),
            confidence=round(float(latest_evaluation.confidence), 2),
            replan_count=diagnostics.replans if diagnostics else 0,
            should_replan=bool(latest_evaluation.should_replan),
            missing_requirements_count=len(latest_evaluation.missing_requirements),
            contradictions_count=len(latest_evaluation.contradictions),
        ).model_dump()
    elif diagnostics and diagnostics.evaluation_count > 0:
        eval_diag = SanitizedAgentEvaluationDiagnostic(
            decision="SUFFICIENT"
            if not diagnostics.failed_tasks
            else "PARTIAL_OR_FAILED",
            confidence=1.0,
            replan_count=diagnostics.replans,
            should_replan=False,
            missing_requirements_count=0,
            contradictions_count=0,
        ).model_dump()

    evidence_count = (
        diagnostics.research_evidence_count
        if diagnostics
        else sum(len(r.evidence) for r in results if r.success)
    )
    plan_reasoning = (
        str(plan.reasoning_summary)[:200] if plan and plan.reasoning_summary else None
    )

    latencies = {
        "planning_latency_ms": round(diagnostics.planning_latency_ms, 2)
        if diagnostics
        else 0.0,
        "routing_latency_ms": round(diagnostics.routing_latency_ms, 2)
        if diagnostics
        else 0.0,
        "execution_latency_ms": round(diagnostics.execution_latency_ms, 2)
        if diagnostics
        else 0.0,
        "evaluation_latency_ms": round(diagnostics.evaluation_latency_ms, 2)
        if diagnostics
        else 0.0,
        "synthesis_latency_ms": round(diagnostics.synthesis_latency_ms, 2)
        if diagnostics
        else 0.0,
    }

    sanitized = SanitizedAgentDiagnostics(
        multi_agent_execution=True,
        plan_reasoning=plan_reasoning,
        plan_iterations=diagnostics.plan_iterations
        if diagnostics
        else (plan.iteration if plan else 1),
        total_specialist_calls=diagnostics.total_specialist_calls
        if diagnostics
        else len(results),
        total_time_ms=round(total_time_ms, 2),
        tasks=[SanitizedAgentTaskDiagnostic(**t) for t in tasks_sanitized],
        evaluation=SanitizedAgentEvaluationDiagnostic(**eval_diag)
        if eval_diag
        else None,
        concurrency_savings_ms=round(diagnostics.concurrency_savings_ms, 2)
        if diagnostics
        else 0.0,
        limits_reached=list(diagnostics.limits_reached) if diagnostics else [],
        evidence_count=evidence_count,
        citation_count=citation_count,
        avoided_duplicate_tasks=diagnostics.avoided_duplicate_tasks
        if diagnostics
        else 0,
        latencies=latencies,
    )

    return sanitized.model_dump()
