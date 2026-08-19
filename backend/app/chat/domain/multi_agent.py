from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.chat.domain.models import Citation, Usage


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


class MultiAgentDiagnostics(BaseModel):
    plan_iterations: int = 1
    total_specialist_calls: int = 0
    concurrency_savings_ms: float = 0.0
    task_latencies: dict[str, float] = Field(default_factory=dict)
    failed_tasks: list[str] = Field(default_factory=list)
    limits_reached: list[str] = Field(default_factory=list)


class MultiAgentResponse(BaseModel):
    answer: str
    plan: ExecutionPlan
    specialist_results: list[AgentResult]
    citations: list[Citation] = Field(default_factory=list)
    usage: Usage
    total_time_ms: float
    diagnostics: MultiAgentDiagnostics
