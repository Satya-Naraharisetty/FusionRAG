import logging
from uuid import UUID

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class OrchestrationTelemetryEvent(BaseModel):
    """
    Sanitized structured telemetry event for an Adaptive RAG orchestration.
    Guarantees that raw document contents, user secrets, and chain-of-thought are never logged.
    """

    orchestration_id: UUID
    query_type: str
    selected_strategy: str
    strategy_confidence: float
    task_count: int
    completed_task_count: int
    failed_task_count: int
    replan_count: int
    retrieval_call_count: int
    hyde_used: bool = False
    hyde_latency_ms: float = 0.0
    expansion_used: bool = False
    decomposition_used: bool = False
    evidence_sufficiency_score: float = 1.0
    missing_evidence_count: int = 0
    duplicate_task_count: int = 0
    conflict_detected: bool = False
    conflict_resolved: bool = False
    final_status: str
    total_latency_ms: float

    model_config = ConfigDict(frozen=True)


class OrchestrationTelemetry:
    """
    Telemetry recorder emitting sanitized telemetry metrics.
    """

    def __init__(self) -> None:
        self._history: list[OrchestrationTelemetryEvent] = []

    def record(self, event: OrchestrationTelemetryEvent) -> None:
        self._history.append(event)
        logger.info(
            f"AdaptiveRAG Telemetry [id: {event.orchestration_id}, strategy: {event.selected_strategy}, "
            f"status: {event.final_status}] - tasks: {event.task_count}, completed: {event.completed_task_count}, "
            f"calls: {event.retrieval_call_count}, replans: {event.replan_count}, "
            f"hyde: {event.hyde_used}, latency: {event.total_latency_ms:.2f}ms"
        )

    def get_history(self) -> list[OrchestrationTelemetryEvent]:
        return list(self._history)
