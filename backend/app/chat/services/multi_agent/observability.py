import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from collections import deque
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.chat.domain.agent_observability import (
    AgentErrorRecord,
    AgentQualityMetrics,
    AgentSecurityEvent,
    AgentTaskTrace,
    AgentTrace,
    AgentTraceEvent,
    AgentTraceStatus,
    BatchExecutionTrace,
    FailureCategory,
    ProviderUsageRecord,
    hash_user_id,
    sanitize_telemetry_data,
)
from app.chat.domain.multi_agent import (
    MultiAgentDiagnostics,
    ResultEvaluation,
    RoutingDecision,
)

logger = logging.getLogger(__name__)


class AgentTelemetrySink(ABC):
    """Abstract telemetry destination interface for multi-agent observability."""

    @abstractmethod
    async def emit_event(self, event: AgentTraceEvent) -> None:
        pass

    @abstractmethod
    async def record_metric(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        pass

    @abstractmethod
    async def record_trace(self, trace: AgentTrace) -> None:
        pass

    @abstractmethod
    async def record_security_event(self, event: AgentSecurityEvent) -> None:
        pass


class InMemoryTelemetrySink(AgentTelemetrySink):
    """
    Default in-memory telemetry sink for development, testing, and diagnostics.
    Maintains bounded thread-safe in-memory collections of traces, events, metrics, and security audits.
    """

    def __init__(self, max_traces: int = 100, max_events: int = 2000) -> None:
        self.max_traces = max_traces
        self.max_events = max_events
        self.traces: deque[AgentTrace] = deque(maxlen=max_traces)
        self.events: deque[AgentTraceEvent] = deque(maxlen=max_events)
        self.security_events: deque[AgentSecurityEvent] = deque(maxlen=max_events)
        self.metrics: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def emit_event(self, event: AgentTraceEvent) -> None:
        async with self._lock:
            self.events.append(event)

    async def record_metric(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        async with self._lock:
            self.metrics.append(
                {
                    "name": name,
                    "value": value,
                    "tags": tags or {},
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

    async def record_trace(self, trace: AgentTrace) -> None:
        async with self._lock:
            self.traces.append(trace)

    async def record_security_event(self, event: AgentSecurityEvent) -> None:
        async with self._lock:
            self.security_events.append(event)

    def get_traces(self) -> list[AgentTrace]:
        return list(self.traces)

    def get_trace_by_id(self, request_id: str) -> AgentTrace | None:
        for t in self.traces:
            if t.request_id == request_id:
                return t
        return None

    def get_events(self, request_id: str | None = None) -> list[AgentTraceEvent]:
        if request_id is None:
            return list(self.events)
        return [e for e in self.events if e.request_id == request_id]

    def get_security_events(
        self, request_id: str | None = None
    ) -> list[AgentSecurityEvent]:
        if request_id is None:
            return list(self.security_events)
        return [
            s for s in self.security_events if s.details.get("request_id") == request_id
        ]

    def clear(self) -> None:
        self.traces.clear()
        self.events.clear()
        self.security_events.clear()
        self.metrics.clear()


class AgentObservabilityService:
    """
    Central production observability service for the multi-agent system.
    Manages in-memory request-local trace tracking, lifecycle event recording,
    performance & concurrency metrics calculation, failure classification,
    strict recursive redaction, and decoupled sink emission.
    Guaranteed fail-open: telemetry errors never crash user requests.
    """

    def __init__(
        self,
        sink: AgentTelemetrySink | None = None,
        enabled: bool = True,
        max_events: int = 500,
        max_tasks: int = 50,
        max_str_len: int = 500,
        max_keys: int = 50,
    ) -> None:
        self.sink = sink or InMemoryTelemetrySink()
        self.enabled = enabled
        self.max_events = max_events
        self.max_tasks = max_tasks
        self.max_str_len = max_str_len
        self.max_keys = max_keys
        self._active_traces: dict[str, AgentTrace] = {}

    def _sanitize(self, data: Any) -> Any:
        return sanitize_telemetry_data(
            data, max_str_len=self.max_str_len, max_keys=self.max_keys
        )

    def start_trace(
        self,
        request_id: str,
        conversation_id: str | UUID | None = None,
        user_id: str | UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentTrace | None:
        """Initializes a request-local trace."""
        if not self.enabled:
            return None
        try:
            conv_id_str = str(conversation_id) if conversation_id else None
            user_id_h = hash_user_id(user_id)
            safe_meta = self._sanitize(metadata or {})

            trace = AgentTrace(
                request_id=request_id,
                conversation_id=conv_id_str,
                user_id_hash=user_id_h,
                started_at=datetime.now(UTC),
                status=AgentTraceStatus.RUNNING,
                metadata=safe_meta,
            )
            self._active_traces[request_id] = trace

            self.record_event(
                request_id=request_id,
                event_type="request_started",
                metadata={"conversation_id": conv_id_str},
            )
            return trace
        except Exception as e:
            logger.warning(
                "Failed to start agent trace for request %s: %s", request_id, e
            )
            return None

    def record_event(
        self,
        request_id: str,
        event_type: str,
        task_id: str | None = None,
        agent_type: str | None = None,
        capability_id: str | None = None,
        duration_ms: float | None = None,
        status: str = "ok",
        metadata: dict[str, Any] | None = None,
    ) -> AgentTraceEvent | None:
        """Appends a structured lifecycle event to the active trace and emits to the telemetry sink."""
        if not self.enabled:
            return None
        try:
            event = AgentTraceEvent(
                event_id=str(uuid.uuid4()),
                request_id=request_id,
                timestamp=datetime.now(UTC),
                event_type=event_type,
                task_id=task_id,
                agent_type=agent_type,
                capability_id=capability_id,
                duration_ms=duration_ms,
                status=status,
                metadata=self._sanitize(metadata or {}),
            )

            trace = self._active_traces.get(request_id)
            if trace and len(trace.events) < self.max_events:
                trace.events.append(event)

            # Fire and forget emission to sink
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.sink.emit_event(event))
            except RuntimeError:
                pass

            return event
        except Exception as e:
            logger.debug("Failed to record agent event %s: %s", event_type, e)
            return None

    def start_task(
        self,
        request_id: str,
        task_id: str,
        agent_type: str,
        dependencies: list[str] | None = None,
        capability_id: str | None = None,
        estimated_latency_ms: float = 0.0,
        estimated_cost_units: float = 0.0,
        parent_task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Records task commencement and initial resource estimates."""
        if not self.enabled:
            return
        try:
            trace = self._active_traces.get(request_id)
            if not trace:
                return

            if len(trace.tasks) >= self.max_tasks:
                return

            task_trace = AgentTaskTrace(
                task_id=task_id,
                agent_type=agent_type,
                capability_id=capability_id,
                status="RUNNING",
                parent_task_id=parent_task_id,
                dependencies=list(dependencies or []),
                estimated_latency_ms=estimated_latency_ms,
                estimated_cost_units=estimated_cost_units,
                metadata=self._sanitize(metadata or {}),
            )
            trace.tasks.append(task_trace)
            trace.estimated_cost_units += estimated_cost_units

            self.record_event(
                request_id=request_id,
                event_type="task_started",
                task_id=task_id,
                agent_type=agent_type,
                capability_id=capability_id,
                metadata={"parent_task_id": parent_task_id},
            )
        except Exception as e:
            logger.debug("Failed to record start_task for %s: %s", task_id, e)

    def complete_task(
        self,
        request_id: str,
        task_id: str,
        actual_latency_ms: float = 0.0,
        execution_ms: float = 0.0,
        queue_wait_ms: float = 0.0,
        evidence_count: int = 0,
        citations_count: int = 0,
        provider_usage: ProviderUsageRecord | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Records successful task execution metrics."""
        if not self.enabled:
            return
        try:
            trace = self._active_traces.get(request_id)
            if not trace:
                return

            task_trace = next((t for t in trace.tasks if t.task_id == task_id), None)
            if task_trace:
                task_trace.status = "COMPLETED"
                task_trace.actual_latency_ms = actual_latency_ms
                task_trace.execution_ms = execution_ms or actual_latency_ms
                task_trace.queue_wait_ms = queue_wait_ms
                task_trace.evidence_count = evidence_count
                task_trace.citations_count = citations_count
                if provider_usage:
                    task_trace.provider_usage = provider_usage
                    trace.actual_input_tokens += provider_usage.input_tokens
                    trace.actual_output_tokens += provider_usage.output_tokens
                    trace.actual_total_tokens += provider_usage.total_tokens
                if metadata:
                    task_trace.metadata.update(self._sanitize(metadata))

            trace.quality_metrics.successful_task_count += 1

            self.record_event(
                request_id=request_id,
                event_type="task_completed",
                task_id=task_id,
                duration_ms=actual_latency_ms,
                status="COMPLETED",
                metadata={
                    "evidence_count": evidence_count,
                    "citations_count": citations_count,
                },
            )
        except Exception as e:
            logger.debug("Failed to record complete_task for %s: %s", task_id, e)

    def fail_task(
        self,
        request_id: str,
        task_id: str,
        failure_category: FailureCategory = FailureCategory.UNKNOWN_ERROR,
        failure_reason: str = "",
        safe_error_message: str = "",
        retryable: bool = False,
        actual_latency_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Records task failure with structured classification."""
        if not self.enabled:
            return
        try:
            trace = self._active_traces.get(request_id)
            if not trace:
                return

            error_record = AgentErrorRecord(
                failure_category=failure_category,
                task_id=task_id,
                retryable=retryable,
                failure_reason=failure_reason or failure_category.value,
                safe_error_message=self._sanitize(
                    safe_error_message or "Task failed execution."
                ),
                metadata=self._sanitize(metadata or {}),
            )
            trace.errors.append(error_record)

            task_trace = next((t for t in trace.tasks if t.task_id == task_id), None)
            if task_trace:
                task_trace.status = "FAILED"
                task_trace.actual_latency_ms = actual_latency_ms
                task_trace.failure_record = error_record
                if metadata:
                    task_trace.metadata.update(self._sanitize(metadata))

            trace.quality_metrics.failed_task_count += 1

            self.record_event(
                request_id=request_id,
                event_type="task_failed",
                task_id=task_id,
                duration_ms=actual_latency_ms,
                status="FAILED",
                metadata={
                    "failure_category": failure_category.value,
                    "failure_reason": failure_reason,
                    "retryable": retryable,
                },
            )
        except Exception as e:
            logger.debug("Failed to record fail_task for %s: %s", task_id, e)

    def skip_task(
        self,
        request_id: str,
        task_id: str,
        agent_type: str = "UNKNOWN",
        reason: str = "",
        failure_category: FailureCategory = FailureCategory.DEPENDENCY_FAILED,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Records a skipped task (e.g. due to upstream dependency failure or hard limits)."""
        if not self.enabled:
            return
        try:
            trace = self._active_traces.get(request_id)
            if not trace:
                return

            task_trace = next((t for t in trace.tasks if t.task_id == task_id), None)
            if not task_trace and len(trace.tasks) < self.max_tasks:
                task_trace = AgentTaskTrace(
                    task_id=task_id,
                    agent_type=agent_type,
                    status="SKIPPED",
                    metadata=self._sanitize(metadata or {}),
                )
                trace.tasks.append(task_trace)
            elif task_trace:
                task_trace.status = "SKIPPED"
                if metadata:
                    task_trace.metadata.update(self._sanitize(metadata))

            trace.quality_metrics.skipped_task_count += 1

            self.record_event(
                request_id=request_id,
                event_type="task_skipped",
                task_id=task_id,
                agent_type=agent_type,
                status="SKIPPED",
                metadata={"reason": reason, "failure_category": failure_category.value},
            )
        except Exception as e:
            logger.debug("Failed to record skip_task for %s: %s", task_id, e)

    def record_routing_decision(
        self,
        request_id: str,
        task_id: str,
        decision: RoutingDecision,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Records a capability routing decision or rejection."""
        if not self.enabled:
            return
        try:
            trace = self._active_traces.get(request_id)
            if decision.selected_capability_id:
                if trace:
                    task_trace = next(
                        (t for t in trace.tasks if t.task_id == task_id), None
                    )
                    if task_trace:
                        task_trace.capability_id = decision.selected_capability_id
                        task_trace.estimated_latency_ms = decision.estimated_latency_ms
                        task_trace.estimated_cost_units = decision.estimated_cost_units
                self.record_event(
                    request_id=request_id,
                    event_type="routing_completed",
                    task_id=task_id,
                    capability_id=decision.selected_capability_id,
                    metadata={
                        "reason_code": decision.reason_code,
                        "estimated_latency_ms": decision.estimated_latency_ms,
                        "estimated_cost_units": decision.estimated_cost_units,
                        **(self._sanitize(metadata or {})),
                    },
                )
            else:
                self.record_event(
                    request_id=request_id,
                    event_type="routing_rejected",
                    task_id=task_id,
                    status="REJECTED",
                    metadata={
                        "reason_code": decision.reason_code,
                        **(self._sanitize(metadata or {})),
                    },
                )
        except Exception as e:
            logger.debug("Failed to record routing decision for %s: %s", task_id, e)

    def record_batch_execution(
        self,
        request_id: str,
        batch_id: str,
        task_ids: list[str],
        estimated_sequential_latency_ms: float,
        estimated_parallel_latency_ms: float,
        actual_sequential_equivalent_ms: float,
        actual_parallel_wall_clock_ms: float,
    ) -> BatchExecutionTrace | None:
        """
        Records batch execution and calculates rigorous concurrency metrics:
        - estimated_concurrency_savings_ms = max(0, est_seq - est_par)
        - actual_concurrency_savings_ms = max(0, act_seq - act_wall_clock)
        """
        if not self.enabled:
            return None
        try:
            trace = self._active_traces.get(request_id)
            if not trace:
                return None

            est_savings = max(
                0.0, estimated_sequential_latency_ms - estimated_parallel_latency_ms
            )
            act_savings = max(
                0.0, actual_sequential_equivalent_ms - actual_parallel_wall_clock_ms
            )

            batch_trace = BatchExecutionTrace(
                batch_id=batch_id,
                task_ids=task_ids,
                task_count=len(task_ids),
                estimated_sequential_latency_ms=estimated_sequential_latency_ms,
                estimated_parallel_latency_ms=estimated_parallel_latency_ms,
                estimated_concurrency_savings_ms=est_savings,
                actual_sequential_equivalent_ms=actual_sequential_equivalent_ms,
                actual_parallel_wall_clock_ms=actual_parallel_wall_clock_ms,
                actual_concurrency_savings_ms=act_savings,
            )
            trace.batches.append(batch_trace)
            trace.quality_metrics.number_of_parallel_batches += 1
            return batch_trace
        except Exception as e:
            logger.debug("Failed to record batch execution: %s", e)
            return None

    def record_evaluation(
        self,
        request_id: str,
        evaluation: ResultEvaluation,
        duration_ms: float = 0.0,
    ) -> None:
        """Records result evaluation metrics."""
        if not self.enabled:
            return
        try:
            trace = self._active_traces.get(request_id)
            if trace:
                trace.quality_metrics.evaluation_count += 1
                trace.evaluation_latency_ms += duration_ms

            self.record_event(
                request_id=request_id,
                event_type="evaluation_completed",
                duration_ms=duration_ms,
                status=evaluation.decision.value,
                metadata={
                    "confidence": evaluation.confidence,
                    "evidence_count": evaluation.evidence_count,
                    "should_replan": evaluation.should_replan,
                    "missing_count": len(evaluation.missing_requirements),
                    "contradictions_count": len(evaluation.contradictions),
                },
            )
        except Exception as e:
            logger.debug("Failed to record evaluation: %s", e)

    def record_replan(
        self,
        request_id: str,
        iteration: int,
        new_tasks_count: int = 0,
        preserved_tasks_count: int = 0,
        avoided_dupes: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        """Records adaptive replanning iteration telemetry."""
        if not self.enabled:
            return
        try:
            trace = self._active_traces.get(request_id)
            if trace:
                trace.total_replans += 1
                trace.quality_metrics.number_of_replans += 1

            self.record_event(
                request_id=request_id,
                event_type="replan_completed",
                duration_ms=duration_ms,
                metadata={
                    "iteration": iteration,
                    "new_tasks_count": new_tasks_count,
                    "preserved_tasks_count": preserved_tasks_count,
                    "avoided_duplicates": avoided_dupes,
                },
            )
        except Exception as e:
            logger.debug("Failed to record replan: %s", e)

    def record_security_event(
        self,
        request_id: str,
        event_type: str,
        reason: str,
        task_id: str | None = None,
        agent_type: str | None = None,
        user_id: str | UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> AgentSecurityEvent | None:
        """Records a security policy audit event with strict redaction."""
        if not self.enabled:
            return None
        try:
            safe_details = self._sanitize(details or {})
            safe_details["request_id"] = request_id

            sec_event = AgentSecurityEvent(
                event_type=event_type,
                reason=reason,
                task_id=task_id,
                agent_type=agent_type,
                user_id_hash=hash_user_id(user_id),
                details=safe_details,
                timestamp=datetime.now(UTC),
            )

            trace = self._active_traces.get(request_id)
            if trace:
                trace.security_events.append(sec_event)

            self.record_event(
                request_id=request_id,
                event_type="security_policy_rejected",
                task_id=task_id,
                agent_type=agent_type,
                status="REJECTED",
                metadata={"reason": reason, "sec_event_type": event_type},
            )

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.sink.record_security_event(sec_event))
            except RuntimeError:
                pass

            return sec_event
        except Exception as e:
            logger.warning("Failed to record security event: %s", e)
            return None

    def record_evidence_metrics(
        self,
        request_id: str,
        total_evidence: int = 0,
        unique_evidence: int = 0,
        duplicate_removed: int = 0,
        citation_count: int = 0,
        unsupported_count: int = 0,
        conflicting_count: int = 0,
        empty_retrieval_count: int = 0,
        research_subqueries: int = 0,
        successful_research_subqueries: int = 0,
        failed_research_subqueries: int = 0,
        citations_received: int = 0,
        citations_returned: int = 0,
        grounding_status: str = "grounded",
    ) -> None:
        """Updates evidence quality and grounding metrics on the trace."""
        if not self.enabled:
            return
        try:
            trace = self._active_traces.get(request_id)
            if not trace:
                return

            ev = trace.evidence_metrics
            ev.total_evidence_items = total_evidence
            ev.unique_evidence_items = unique_evidence
            ev.duplicate_evidence_removed = duplicate_removed
            ev.citation_count = citation_count
            ev.unsupported_evidence_count = unsupported_count
            ev.conflicting_evidence_count = conflicting_count
            ev.empty_retrieval_count = empty_retrieval_count
            ev.research_subqueries = research_subqueries
            ev.successful_research_subqueries = successful_research_subqueries
            ev.failed_research_subqueries = failed_research_subqueries
            ev.citations_received = citations_received
            ev.citations_returned = citations_returned
            ev.evidence_grounding_status = grounding_status
            trace.quality_metrics.final_grounding_status = grounding_status
        except Exception as e:
            logger.debug("Failed to record evidence metrics: %s", e)

    def complete_trace(
        self,
        request_id: str,
        diagnostics: MultiAgentDiagnostics | None = None,
        quality_metrics: AgentQualityMetrics | None = None,
        status: AgentTraceStatus = AgentTraceStatus.COMPLETED,
    ) -> AgentTrace | None:
        """Completes the trace, calculates aggregated latencies, and emits to the telemetry sink."""
        if not self.enabled:
            return None
        try:
            trace = self._active_traces.pop(request_id, None)
            if not trace:
                return None

            trace.completed_at = datetime.now(UTC)
            trace.status = status

            if diagnostics:
                trace.planning_latency_ms = diagnostics.planning_latency_ms
                trace.routing_latency_ms = diagnostics.routing_latency_ms
                trace.execution_latency_ms = diagnostics.execution_latency_ms
                trace.evaluation_latency_ms = diagnostics.evaluation_latency_ms
                trace.synthesis_latency_ms = diagnostics.synthesis_latency_ms
                trace.total_agent_calls = diagnostics.total_specialist_calls
                trace.total_replans = diagnostics.replans
                trace.estimated_cost_units = diagnostics.estimated_cost_units
                trace.estimated_latency_ms = diagnostics.estimated_latency_ms

            if quality_metrics:
                trace.quality_metrics = quality_metrics

            # Calculate total wall-clock latency
            started = trace.started_at
            completed = trace.completed_at
            if started and completed:
                trace.total_latency_ms = (completed - started).total_seconds() * 1000.0
                trace.actual_latency_ms = trace.total_latency_ms

            # Deduce specialist count if not explicitly set
            if quality_metrics and quality_metrics.number_of_specialists_used > 0:
                pass
            else:
                specialists_used = {
                    t.agent_type for t in trace.tasks if t.status == "COMPLETED"
                }
                trace.quality_metrics.number_of_specialists_used = len(specialists_used)

            self.record_event(
                request_id=request_id,
                event_type="request_completed",
                duration_ms=trace.total_latency_ms,
                status=status.value,
            )

            if isinstance(self.sink, InMemoryTelemetrySink):
                self.sink.traces.append(trace)

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.sink.record_trace(trace))
            except RuntimeError:
                pass

            return trace
        except Exception as e:
            logger.warning(
                "Failed to complete agent trace for request %s: %s", request_id, e
            )
            return None

    def fail_trace(
        self,
        request_id: str,
        failure_category: FailureCategory = FailureCategory.UNKNOWN_ERROR,
        error_message: str = "",
        diagnostics: MultiAgentDiagnostics | None = None,
    ) -> AgentTrace | None:
        """Marks a trace as failed and records the terminal error."""
        if not self.enabled:
            return None
        try:
            trace = self._active_traces.get(request_id)
            if trace:
                error_record = AgentErrorRecord(
                    failure_category=failure_category,
                    failure_reason=failure_category.value,
                    safe_error_message=self._sanitize(
                        error_message or "Request execution failed."
                    ),
                )
                trace.errors.append(error_record)
                trace.quality_metrics.planning_success = False

            self.record_event(
                request_id=request_id,
                event_type="request_failed",
                status="FAILED",
                metadata={"failure_category": failure_category.value},
            )
            return self.complete_trace(
                request_id=request_id,
                diagnostics=diagnostics,
                status=AgentTraceStatus.FAILED,
            )
        except Exception as e:
            logger.warning(
                "Failed to fail agent trace for request %s: %s", request_id, e
            )
            return None

    def get_trace(self, request_id: str) -> AgentTrace | None:
        """Retrieves an active or completed trace (from active memory or sink)."""
        if request_id in self._active_traces:
            return self._active_traces[request_id]
        if isinstance(self.sink, InMemoryTelemetrySink):
            return self.sink.get_trace_by_id(request_id)
        return None
