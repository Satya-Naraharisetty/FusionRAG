from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.chat.domain.models import Citation, Usage
from app.documents.domain.models import DocumentRetrievalScope


class AgentType(str, Enum):
    MASTER = "MASTER"
    RESEARCH = "RESEARCH"
    DOCUMENT = "DOCUMENT"
    ANALYSIS = "ANALYSIS"
    SYNTHESIS = "SYNTHESIS"


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


class MultiAgentResponse(BaseModel):
    answer: str
    plan: ExecutionPlan
    specialist_results: list[AgentResult]
    citations: list[Citation] = Field(default_factory=list)
    usage: Usage
    total_time_ms: float
    diagnostics: MultiAgentDiagnostics
