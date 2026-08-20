import hashlib
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# Sensitive key names that must be redacted recursively
SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "password",
    "credential",
    "credentials",
    "prompt",
    "system_prompt",
    "developer_prompt",
    "document_content",
    "chunk_content",
    "raw_prompt",
    "chain_of_thought",
}


def hash_user_id(user_id: UUID | str | None) -> str | None:
    """Produces a non-reversible SHA-256 hash of user ID for privacy-safe telemetry correlation."""
    if not user_id:
        return None
    raw = str(user_id).strip()
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def sanitize_telemetry_data(
    data: Any,
    max_str_len: int = 500,
    max_keys: int = 50,
    depth: int = 0,
    max_depth: int = 5,
) -> Any:
    """
    Recursively sanitizes dictionaries, lists, models, and payloads for telemetry storage.
    Redacts credentials, tokens, passwords, raw prompts, and full document contents.
    Enforces maximum string lengths, collection sizes, and recursion depth to prevent memory bloating.
    """
    if depth > max_depth:
        return "[TRUNCATED_DEPTH]"

    if data is None:
        return None

    if isinstance(data, (bool, int, float)):
        return data

    if isinstance(data, datetime):
        return data.isoformat()

    if isinstance(data, UUID):
        return str(data)

    if isinstance(data, str):
        if len(data) > max_str_len:
            return data[:max_str_len] + "...[TRUNCATED]"
        return data

    if isinstance(data, BaseModel):
        data = data.model_dump()

    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for idx, (k, v) in enumerate(data.items()):
            if idx >= max_keys:
                sanitized["_truncated_keys_count"] = len(data) - max_keys
                break
            key_str = str(k).lower().strip()
            if any(s in key_str for s in SENSITIVE_KEYS):
                sanitized[str(k)] = "[REDACTED]"
            else:
                sanitized[str(k)] = sanitize_telemetry_data(
                    v, max_str_len, max_keys, depth + 1, max_depth
                )
        return sanitized

    if isinstance(data, (list, tuple, set)):
        items = list(data)
        sanitized_list: list[Any] = []
        for idx, item in enumerate(items):
            if idx >= max_keys:
                sanitized_list.append(f"[+{len(items) - max_keys} MORE ITEMS]")
                break
            sanitized_list.append(
                sanitize_telemetry_data(
                    item, max_str_len, max_keys, depth + 1, max_depth
                )
            )
        return sanitized_list

    # Fallback string representation
    str_repr = str(data)
    if len(str_repr) > max_str_len:
        return str_repr[:max_str_len] + "...[TRUNCATED]"
    return str_repr


class AgentPhase(str, Enum):
    PLANNING = "PLANNING"
    ROUTING = "ROUTING"
    EXECUTION = "EXECUTION"
    EVALUATION = "EVALUATION"
    REPLANNING = "REPLANNING"
    SYNTHESIS = "SYNTHESIS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentTraceStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class FailureCategory(str, Enum):
    PLANNING_FAILURE = "PLANNING_FAILURE"
    PLAN_VALIDATION_FAILURE = "PLAN_VALIDATION_FAILURE"
    ROUTING_FAILURE = "ROUTING_FAILURE"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    DEPENDENCY_FAILED = "DEPENDENCY_FAILED"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
    SYNTHESIS_ERROR = "SYNTHESIS_ERROR"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class AgentErrorRecord(BaseModel):
    failure_category: FailureCategory
    task_id: str | None = None
    agent_type: str | None = None
    capability_id: str | None = None
    retryable: bool = False
    failure_reason: str = ""
    safe_error_message: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSecurityEvent(BaseModel):
    event_type: str
    reason: str
    task_id: str | None = None
    agent_type: str | None = None
    user_id_hash: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentTraceEvent(BaseModel):
    event_id: str
    request_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    task_id: str | None = None
    agent_type: str | None = None
    capability_id: str | None = None
    duration_ms: float | None = None
    status: str = "ok"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderUsageRecord(BaseModel):
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    provider_latency_ms: float = 0.0
    finish_reason: str | None = None


class AgentTaskTrace(BaseModel):
    task_id: str
    agent_type: str
    capability_id: str | None = None
    status: str = "PENDING"
    parent_task_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    estimated_latency_ms: float = 0.0
    actual_latency_ms: float = 0.0
    estimated_cost_units: float = 0.0
    queue_wait_ms: float = 0.0
    execution_ms: float = 0.0
    retry_count: int = 0
    retry_reason: str | None = None
    evidence_count: int = 0
    citations_count: int = 0
    provider_usage: ProviderUsageRecord | None = None
    failure_record: AgentErrorRecord | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BatchExecutionTrace(BaseModel):
    batch_id: str
    task_ids: list[str] = Field(default_factory=list)
    task_count: int = 0
    estimated_sequential_latency_ms: float = 0.0
    estimated_parallel_latency_ms: float = 0.0
    estimated_concurrency_savings_ms: float = 0.0
    actual_sequential_equivalent_ms: float = 0.0
    actual_parallel_wall_clock_ms: float = 0.0
    actual_concurrency_savings_ms: float = 0.0


class AgentEvidenceMetrics(BaseModel):
    total_evidence_items: int = 0
    unique_evidence_items: int = 0
    duplicate_evidence_removed: int = 0
    citation_count: int = 0
    unsupported_evidence_count: int = 0
    conflicting_evidence_count: int = 0
    empty_retrieval_count: int = 0
    research_subqueries: int = 0
    successful_research_subqueries: int = 0
    failed_research_subqueries: int = 0
    citations_received: int = 0
    citations_returned: int = 0
    evidence_grounding_status: str = "grounded"


class AgentQualityMetrics(BaseModel):
    planning_success: bool = True
    planning_fallback_used: bool = False
    number_of_specialists_used: int = 0
    number_of_parallel_batches: int = 0
    number_of_replans: int = 0
    successful_task_count: int = 0
    failed_task_count: int = 0
    skipped_task_count: int = 0
    capability_fallback_count: int = 0
    evaluation_count: int = 0
    synthesis_success: bool = True
    final_grounding_status: str = "grounded"


class AgentTrace(BaseModel):
    request_id: str
    conversation_id: str | None = None
    user_id_hash: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    status: AgentTraceStatus = AgentTraceStatus.RUNNING
    total_latency_ms: float = 0.0
    planning_latency_ms: float = 0.0
    routing_latency_ms: float = 0.0
    execution_latency_ms: float = 0.0
    evaluation_latency_ms: float = 0.0
    synthesis_latency_ms: float = 0.0
    total_agent_calls: int = 0
    total_replans: int = 0
    estimated_cost_units: float = 0.0
    estimated_latency_ms: float = 0.0
    actual_latency_ms: float = 0.0
    actual_input_tokens: int = 0
    actual_output_tokens: int = 0
    actual_total_tokens: int = 0
    tasks: list[AgentTaskTrace] = Field(default_factory=list)
    batches: list[BatchExecutionTrace] = Field(default_factory=list)
    events: list[AgentTraceEvent] = Field(default_factory=list)
    errors: list[AgentErrorRecord] = Field(default_factory=list)
    security_events: list[AgentSecurityEvent] = Field(default_factory=list)
    evidence_metrics: AgentEvidenceMetrics = Field(default_factory=AgentEvidenceMetrics)
    quality_metrics: AgentQualityMetrics = Field(default_factory=AgentQualityMetrics)
    metadata: dict[str, Any] = Field(default_factory=dict)
