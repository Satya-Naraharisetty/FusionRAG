import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.chat.domain.agent_observability import (
    AgentQualityMetrics,
    AgentTraceStatus,
    FailureCategory,
    hash_user_id,
    sanitize_telemetry_data,
)
from app.chat.domain.models import Usage
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentFailureReason,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
    CapabilityRequirement,
    CapabilityType,
    ExecutionPlan,
)
from app.chat.services.multi_agent.analysis_agent import AnalysisAgent
from app.chat.services.multi_agent.capability_registry import (
    CapabilityRegistry,
    create_default_capability_registry,
)
from app.chat.services.multi_agent.document_agent import DocumentAgent
from app.chat.services.multi_agent.execution_engine import AgentExecutionEngine
from app.chat.services.multi_agent.health_diagnostics import get_agent_readiness_report
from app.chat.services.multi_agent.master_agent import MasterAgent
from app.chat.services.multi_agent.observability import (
    AgentObservabilityService,
    AgentTelemetrySink,
    InMemoryTelemetrySink,
)
from app.chat.services.multi_agent.research_agent import ResearchAgent
from app.chat.services.multi_agent.research_planner import ResearchPlanner
from app.chat.services.multi_agent.result_evaluator import ResultEvaluator
from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent
from app.chat.services.multi_agent.task_router import TaskRouter
from app.documents.domain.models import DocumentScope, RetrievedChunk, SearchResult

# ---------------------------------------------------------------------------
# Test Helpers & Fakes
# ---------------------------------------------------------------------------


class FakeLLMProvider:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.call_history: list[Any] = []

    async def generate(self, messages, model, temperature, max_tokens, **kwargs):
        self.call_history.append(messages)
        content = (
            self.responses.pop(0)
            if self.responses
            else "Synthesized answer based on verified evidence."
        )
        from app.chat.domain.interfaces import ProviderResponse

        return ProviderResponse(
            content=content,
            usage=Usage(prompt_tokens=15, completion_tokens=25, total_tokens=40),
        )


def make_context(
    request_id: str = "req-obs-123",
    user_id: UUID | None = None,
    doc_ids: list[UUID] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AgentExecutionContext:
    return AgentExecutionContext(
        request_id=request_id,
        user_id=user_id or uuid4(),
        conversation_id=uuid4(),
        include_library_documents=False,
        include_conversation_documents=True,
        document_ids=doc_ids or [uuid4()],
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Group A: Trace Lifecycle Tests
# ---------------------------------------------------------------------------


def test_trace_lifecycle_start_and_complete():
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)
    user_id = uuid4()
    req_id = "req-life-1"

    trace = obs.start_trace(
        request_id=req_id,
        conversation_id="conv-1",
        user_id=user_id,
        metadata={"client": "web"},
    )

    assert trace is not None
    assert trace.request_id == req_id
    assert trace.user_id_hash == hash_user_id(user_id)
    assert trace.status == AgentTraceStatus.RUNNING

    obs.start_task(
        request_id=req_id,
        task_id="t1",
        agent_type="RESEARCH",
        estimated_latency_ms=150.0,
        estimated_cost_units=2.0,
    )
    obs.complete_task(
        request_id=req_id,
        task_id="t1",
        actual_latency_ms=120.0,
        evidence_count=3,
        citations_count=2,
    )

    completed_trace = obs.complete_trace(request_id=req_id)
    assert completed_trace is not None
    assert completed_trace.status == AgentTraceStatus.COMPLETED
    assert completed_trace.total_latency_ms >= 0.0
    assert len(completed_trace.tasks) == 1
    assert completed_trace.tasks[0].status == "COMPLETED"
    assert completed_trace.tasks[0].evidence_count == 3


def test_trace_records_failed_request():
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)
    req_id = "req-fail-1"

    obs.start_trace(request_id=req_id)
    failed_trace = obs.fail_trace(
        request_id=req_id,
        failure_category=FailureCategory.TIMEOUT,
        error_message="Global execution timeout exceeded",
    )

    assert failed_trace is not None
    assert failed_trace.status == AgentTraceStatus.FAILED
    assert len(failed_trace.errors) == 1
    assert failed_trace.errors[0].failure_category == FailureCategory.TIMEOUT
    assert (
        failed_trace.errors[0].safe_error_message == "Global execution timeout exceeded"
    )


# ---------------------------------------------------------------------------
# Group B: Event Integrity & Limits Tests
# ---------------------------------------------------------------------------


def test_event_integrity_and_caps():
    sink = InMemoryTelemetrySink()
    # Enforce tight limits to test cap enforcement
    obs = AgentObservabilityService(sink=sink, enabled=True, max_events=3, max_tasks=2)
    req_id = "req-caps-1"

    obs.start_trace(request_id=req_id)  # Event 1: request_started
    obs.record_event(request_id=req_id, event_type="event_2")  # Event 2
    obs.record_event(request_id=req_id, event_type="event_3")  # Event 3
    obs.record_event(
        request_id=req_id, event_type="event_4"
    )  # Should be dropped by cap

    trace = obs.get_trace(req_id)
    assert trace is not None
    assert len(trace.events) == 3
    assert [e.event_type for e in trace.events] == [
        "request_started",
        "event_2",
        "event_3",
    ]

    # Task limit enforcement
    obs.start_task(request_id=req_id, task_id="t1", agent_type="RESEARCH")
    obs.start_task(request_id=req_id, task_id="t2", agent_type="DOCUMENT")
    obs.start_task(
        request_id=req_id, task_id="t3", agent_type="ANALYSIS"
    )  # Dropped by cap
    assert len(trace.tasks) == 2


# ---------------------------------------------------------------------------
# Group C: Performance & Concurrency Metrics Tests
# ---------------------------------------------------------------------------


def test_performance_and_concurrency_metrics_calculation():
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)
    req_id = "req-perf-1"

    obs.start_trace(request_id=req_id)

    # Simulate batch: Task A (est=100ms, act=80ms), Task B (est=200ms, act=190ms)
    # Batch actual wall-clock = 195ms
    obs.start_task(
        request_id=req_id,
        task_id="task_a",
        agent_type="RESEARCH",
        estimated_latency_ms=100.0,
        estimated_cost_units=1.5,
    )
    obs.complete_task(request_id=req_id, task_id="task_a", actual_latency_ms=80.0)

    obs.start_task(
        request_id=req_id,
        task_id="task_b",
        agent_type="DOCUMENT",
        estimated_latency_ms=200.0,
        estimated_cost_units=2.5,
    )
    obs.complete_task(request_id=req_id, task_id="task_b", actual_latency_ms=190.0)

    batch_trace = obs.record_batch_execution(
        request_id=req_id,
        batch_id="batch_1",
        task_ids=["task_a", "task_b"],
        estimated_sequential_latency_ms=300.0,
        estimated_parallel_latency_ms=200.0,
        actual_sequential_equivalent_ms=270.0,
        actual_parallel_wall_clock_ms=195.0,
    )

    assert batch_trace is not None
    # estimated savings = 300 - 200 = 100ms
    assert batch_trace.estimated_concurrency_savings_ms == 100.0
    # actual savings = 270 - 195 = 75ms
    assert batch_trace.actual_concurrency_savings_ms == 75.0

    trace = obs.complete_trace(request_id=req_id)
    assert trace is not None
    assert trace.estimated_cost_units == 4.0  # 1.5 + 2.5
    assert trace.quality_metrics.number_of_parallel_batches == 1


# ---------------------------------------------------------------------------
# Group D: Failure Handling & Taxonomy Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_and_cascading_dependency_failure_propagation():
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)

    # Slow specialist that times out
    slow_specialist = MagicMock()
    slow_specialist.agent_type = AgentType.RESEARCH

    async def slow_execute(task, context):
        await asyncio.sleep(0.5)
        return AgentResult(
            task_id=task.task_id,
            agent_type=AgentType.RESEARCH,
            status=AgentTaskStatus.COMPLETED,
            success=True,
            output="Done",
        )

    slow_specialist.execute_task = AsyncMock(side_effect=slow_execute)

    analysis_specialist = MagicMock()
    analysis_specialist.agent_type = AgentType.ANALYSIS

    engine = AgentExecutionEngine(
        specialist_agents=[slow_specialist, analysis_specialist],
        task_timeout=0.05,  # 50ms timeout
        observability=obs,
    )

    plan = ExecutionPlan(
        request_id="req-fail-dag",
        tasks=[
            AgentTask(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                request="Search",
                dependencies=[],
            ),
            AgentTask(
                task_id="t2",
                agent_type=AgentType.ANALYSIS,
                request="Calculate",
                dependencies=["t1"],
            ),
        ],
    )
    context = make_context(request_id="req-fail-dag")

    obs.start_trace(request_id=context.request_id)
    outcome = await engine.execute(plan, context)

    assert len(outcome.failed_results) == 1
    assert outcome.failed_results[0].task_id == "t1"
    assert outcome.failed_results[0].failure_reason == AgentFailureReason.TIMEOUT

    assert len(outcome.skipped_results) == 1
    assert outcome.skipped_results[0].task_id == "t2"
    assert (
        outcome.skipped_results[0].failure_reason
        == AgentFailureReason.DEPENDENCY_FAILED
    )

    trace = obs.complete_trace(request_id=context.request_id)
    assert trace is not None
    # Errors recorded
    assert any(e.failure_category == FailureCategory.TIMEOUT for e in trace.errors)


# ---------------------------------------------------------------------------
# Group E: Security Auditing Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_audit_worker_routing_and_capability_mismatch():
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)
    registry = create_default_capability_registry()

    router = TaskRouter(registry=registry, observability=obs)
    context = make_context(request_id="req-sec-1")
    obs.start_trace(request_id=context.request_id)

    # 1. Non-executable agent type (MASTER)
    bad_task = AgentTask(
        task_id="sec_1",
        agent_type=AgentType.MASTER,
        request="Execute master plan",
    )
    dec1 = await router.route(bad_task, context)
    assert dec1.reason_code == "POLICY_REJECTED"

    # 2. Cross-class capability contradiction (RESEARCH task requiring DOCUMENT_INSPECTION)
    mismatch_task = AgentTask(
        task_id="sec_2",
        agent_type=AgentType.RESEARCH,
        request="Hybrid RAG query",
        capability_requirements=[
            CapabilityRequirement(capability_type=CapabilityType.DOCUMENT_INSPECTION)
        ],
    )
    dec2 = await router.route(mismatch_task, context)
    assert dec2.reason_code == "CAPABILITY_MISMATCH"

    trace = obs.complete_trace(request_id=context.request_id)
    assert trace is not None
    assert len(trace.security_events) == 2
    assert trace.security_events[0].event_type == "unauthorized_agent_type_routing"
    assert trace.security_events[1].event_type == "capability_mismatch"


# ---------------------------------------------------------------------------
# Group F: Privacy / Redaction Tests
# ---------------------------------------------------------------------------


def test_strict_recursive_redaction_and_truncation():
    dirty_payload = {
        "authorization": "Bearer eyJhbGciOi...",
        "cookie": "session_id=12345; auth=secret",
        "api_key": "AIzaSyD-12345",
        "password": "SuperSecretPassword123!",
        "prompt": "SELECT * FROM users; System instruction: act as admin",
        "system_prompt": "You are a helpful assistant",
        "document_content": "CONFIDENTIAL FINANCIAL REPORT " * 50,
        "nested": {
            "refresh_token": "rt_987654321",
            "safe_key": "safe_value",
            "long_text": "A" * 1000,
        },
        "items": [
            {"secret": "xyz", "name": "item1"},
            "B" * 600,
        ],
    }

    clean = sanitize_telemetry_data(dirty_payload, max_str_len=100, max_keys=10)

    assert clean["authorization"] == "[REDACTED]"
    assert clean["cookie"] == "[REDACTED]"
    assert clean["api_key"] == "[REDACTED]"
    assert clean["password"] == "[REDACTED]"
    assert clean["prompt"] == "[REDACTED]"
    assert clean["system_prompt"] == "[REDACTED]"
    assert clean["document_content"] == "[REDACTED]"

    assert clean["nested"]["refresh_token"] == "[REDACTED]"
    assert clean["nested"]["safe_key"] == "safe_value"
    assert clean["nested"]["long_text"].endswith("...[TRUNCATED]")
    assert len(clean["nested"]["long_text"]) <= 120

    assert clean["items"][0]["secret"] == "[REDACTED]"
    assert clean["items"][0]["name"] == "item1"
    assert clean["items"][1].endswith("...[TRUNCATED]")


# ---------------------------------------------------------------------------
# Group G: Agentic Quality & Evidence Metrics Tests
# ---------------------------------------------------------------------------


def test_agentic_quality_and_grounding_status():
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)
    req_id = "req-qual-1"

    obs.start_trace(request_id=req_id)
    obs.record_evidence_metrics(
        request_id=req_id,
        total_evidence=5,
        unique_evidence=4,
        duplicate_removed=1,
        citation_count=3,
        conflicting_count=0,
        empty_retrieval_count=0,
        research_subqueries=3,
        successful_research_subqueries=3,
        failed_research_subqueries=0,
        citations_received=5,
        citations_returned=3,
        grounding_status="grounded",
    )

    quality = AgentQualityMetrics(
        planning_success=True,
        planning_fallback_used=False,
        number_of_specialists_used=2,
        number_of_replans=0,
        successful_task_count=2,
        failed_task_count=0,
        skipped_task_count=0,
        synthesis_success=True,
        final_grounding_status="grounded",
    )

    trace = obs.complete_trace(request_id=req_id, quality_metrics=quality)
    assert trace is not None
    assert trace.evidence_metrics.duplicate_evidence_removed == 1
    assert trace.evidence_metrics.evidence_grounding_status == "grounded"
    assert trace.quality_metrics.number_of_specialists_used == 2
    assert trace.quality_metrics.planning_success is True


# ---------------------------------------------------------------------------
# Group H: Resilience & Health Diagnostics Tests
# ---------------------------------------------------------------------------


def test_fail_open_telemetry_guarantee():
    # Broken sink that raises an exception on every call
    broken_sink = MagicMock(spec=AgentTelemetrySink)
    broken_sink.emit_event.side_effect = Exception("Sink network failure")
    broken_sink.record_trace.side_effect = Exception("Disk full")

    obs = AgentObservabilityService(sink=broken_sink, enabled=True)

    # Should not raise exception
    trace = obs.start_trace("req-broken")
    obs.record_event("req-broken", "test_event")
    obs.complete_trace("req-broken")
    assert trace is not None


def test_health_readiness_report_safe():
    registry = create_default_capability_registry()
    specialist = MagicMock()
    specialist.agent_type = AgentType.RESEARCH

    report = get_agent_readiness_report(
        capability_registry=registry,
        specialists=[specialist],
        has_llm_provider=True,
        has_retrieval_service=True,
    )

    assert "registered_capabilities" in report
    assert "registered_specialists" in report
    assert "status" in report
    # Ensure no secrets leak in report keys
    assert "api_key" not in report
    assert "password" not in report
    assert "db_url" not in report


# ---------------------------------------------------------------------------
# End-to-End Integration Scenarios (1 through 5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_scenario_1_simple_research():
    """Scenario 1: Simple research request end-to-end trace verification."""
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)

    fake_llm = FakeLLMProvider(
        responses=[
            # Master plan JSON
            '{"tasks": [{"task_id": "r1", "agent_type": "RESEARCH", "request": "What is AI?", "dependencies": []}]}',
            # Research planner JSON
            '{"queries": [{"query_id": "q1", "query": "What is AI?", "priority": 0}]}',
            # Synthesis
            "Artificial Intelligence is the simulation of human intelligence by machines.",
        ]
    )

    doc_id = uuid4()
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="AI_Intro.txt",
        text="AI is machine intelligence.",
        similarity_score=0.92,
        chunk_index=0,
    )
    fake_retrieval = MagicMock()
    fake_retrieval.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="What is AI?",
            retrieval_time=0.01,
            total_matches=1,
            retrieved_chunks=[chunk],
        )
    )

    planner = ResearchPlanner(llm_provider=fake_llm, enable_llm_planner=True)
    research_agent = ResearchAgent(retrieval_service=fake_retrieval, planner=planner)
    doc_agent = DocumentAgent(document_repo=MagicMock())
    analysis_agent = AnalysisAgent()

    engine = AgentExecutionEngine(
        specialist_agents=[research_agent, doc_agent, analysis_agent],
        observability=obs,
    )
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    evaluator = ResultEvaluator()

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        result_evaluator=evaluator,
        observability=obs,
    )

    context = make_context(request_id="req-scen-1", doc_ids=[doc_id])
    resp = await master.execute_request("What is AI?", context)

    assert "Artificial Intelligence" in resp.answer
    trace = obs.get_trace("req-scen-1")
    assert trace is not None
    assert trace.status == AgentTraceStatus.COMPLETED
    assert len(trace.tasks) == 1
    assert trace.tasks[0].agent_type == "RESEARCH"
    assert trace.evidence_metrics.total_evidence_items >= 1
    assert trace.quality_metrics.planning_success is True


@pytest.mark.asyncio
async def test_integration_scenario_2_compound_parallel_request():
    """Scenario 2: Compound parallel request (Research + Document in parallel -> Analysis -> Synthesis)."""
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)

    fake_llm = FakeLLMProvider(
        responses=[
            # Plan: r1 and d1 parallel, a1 depends on both
            '{"tasks": ['
            '{"task_id": "r1", "agent_type": "RESEARCH", "request": "Find Q1 revenue", "dependencies": []},'
            '{"task_id": "d1", "agent_type": "DOCUMENT", "request": "Inspect Q2 doc", "dependencies": [], "parameters": {"document_id": "11111111-1111-1111-1111-111111111111", "action": "inspect"}},'
            '{"task_id": "a1", "agent_type": "ANALYSIS", "request": "Compute growth", "dependencies": ["r1", "d1"], "parameters": {"expression": "200 - 100"}}'
            "]}",
            # Research planner
            '{"queries": [{"query_id": "q1", "query": "Find Q1 revenue"}]}',
            # Synthesis
            "The revenue grew by 100 from Q1 to Q2.",
        ]
    )

    doc_id = UUID("11111111-1111-1111-1111-111111111111")
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="q1.txt",
        text="Q1 revenue was 100",
        similarity_score=0.9,
        chunk_index=0,
    )
    fake_retrieval = MagicMock()
    fake_retrieval.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="Find Q1 revenue",
            retrieval_time=0.01,
            total_matches=1,
            retrieved_chunks=[chunk],
        )
    )

    fake_doc_repo = MagicMock()
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.user_id = UUID("00000000-0000-0000-0000-000000000001")
    mock_doc.scope = DocumentScope.LIBRARY
    mock_doc.filename = "q2.txt"
    mock_doc.original_filename = "q2.txt"
    mock_doc.file_size = 1024
    mock_doc.page_count = 1
    mock_doc.metadata = {"summary": "Q2 revenue was 200"}
    fake_doc_repo.get_by_id = AsyncMock(return_value=mock_doc)

    planner = ResearchPlanner(llm_provider=fake_llm, enable_llm_planner=True)
    research_agent = ResearchAgent(retrieval_service=fake_retrieval, planner=planner)
    doc_agent = DocumentAgent(document_repo=fake_doc_repo)
    analysis_agent = AnalysisAgent()

    engine = AgentExecutionEngine(
        specialist_agents=[research_agent, doc_agent, analysis_agent],
        observability=obs,
    )
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    evaluator = ResultEvaluator()

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        result_evaluator=evaluator,
        observability=obs,
        max_plan_iterations=1,
    )

    context = make_context(
        request_id="req-scen-2",
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        doc_ids=[doc_id],
    )
    resp = await master.execute_request("Compute Q1 to Q2 revenue growth", context)

    assert "100" in resp.answer
    trace = obs.get_trace("req-scen-2")
    assert trace is not None
    # 3 tasks executed
    assert len(trace.tasks) == 3
    # 2 batches executed (Batch 1: r1, d1; Batch 2: a1)
    assert len(trace.batches) == 2
    assert trace.batches[0].task_count == 2
    assert trace.batches[1].task_count == 1


@pytest.mark.asyncio
async def test_integration_scenario_3_insufficient_evidence_and_adaptive_replan():
    """Scenario 3: Insufficient evidence triggers targeted replanning with evidence preservation."""
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)

    fake_llm = FakeLLMProvider(
        responses=[
            # Plan 1: r1
            '{"tasks": [{"task_id": "r1", "agent_type": "RESEARCH", "request": "Find 2024 policy", "dependencies": []}]}',
            # Research planner 1
            '{"queries": [{"query_id": "q1", "query": "2024 policy"}]}',
            # Evaluation 1 LLM response: INSUFFICIENT
            '{"decision": "INSUFFICIENT", "confidence": 0.5, "missing_requirements": [{"requirement": "2025 roadmap", "reason": "missing", "suggested_agent_type": "RESEARCH"}], "contradictions": [], "recommendations": []}',
            # Replanning prompt
            '{"tasks": [{"task_id": "refine_task_2_1", "agent_type": "RESEARCH", "request": "2025 roadmap", "dependencies": []}]}',
            # Research planner 2
            '{"queries": [{"query_id": "q2", "query": "2025 roadmap"}]}',
            # Final Synthesis
            "The 2024 policy and 2025 roadmap are aligned.",
        ]
    )

    doc_id = uuid4()
    chunk1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="p24.txt",
        text="Policy 2024",
        similarity_score=0.88,
        chunk_index=0,
    )
    chunk2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="r25.txt",
        text="Roadmap 2025",
        similarity_score=0.91,
        chunk_index=1,
    )
    fake_retrieval = MagicMock()
    fake_retrieval.retrieve = AsyncMock(
        side_effect=[
            SearchResult(
                original_query="2024 policy",
                retrieval_time=0.01,
                total_matches=1,
                retrieved_chunks=[chunk1],
            ),
            SearchResult(
                original_query="2025 roadmap",
                retrieval_time=0.01,
                total_matches=1,
                retrieved_chunks=[chunk2],
            ),
        ]
    )

    planner = ResearchPlanner(llm_provider=fake_llm, enable_llm_planner=True)
    research_agent = ResearchAgent(retrieval_service=fake_retrieval, planner=planner)
    doc_agent = DocumentAgent(document_repo=MagicMock())
    analysis_agent = AnalysisAgent()

    engine = AgentExecutionEngine(
        specialist_agents=[research_agent, doc_agent, analysis_agent],
        observability=obs,
    )
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    evaluator = ResultEvaluator(llm_provider=fake_llm)

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        result_evaluator=evaluator,
        observability=obs,
        max_plan_iterations=2,
    )

    context = make_context(request_id="req-scen-3", doc_ids=[doc_id])
    resp = await master.execute_request(
        "What is the 2024 policy and 2025 roadmap?", context
    )

    assert "aligned" in resp.answer
    assert resp.diagnostics.replans == 1

    trace = obs.get_trace("req-scen-3")
    assert trace is not None
    assert trace.total_replans == 1
    # Evidence from both iterations preserved
    assert trace.evidence_metrics.total_evidence_items >= 2


@pytest.mark.asyncio
async def test_integration_scenario_4_partial_specialist_failure_isolation():
    """Scenario 4: Partial specialist failure (Research succeeds, Document fails) produces safe grounded synthesis."""
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)

    fake_llm = FakeLLMProvider(
        responses=[
            # Plan: r1 and d1 in parallel
            '{"tasks": ['
            '{"task_id": "r1", "agent_type": "RESEARCH", "request": "Find general background", "dependencies": []},'
            '{"task_id": "d1", "agent_type": "DOCUMENT", "request": "Inspect missing doc", "dependencies": [], "parameters": {"document_id": "00000000-0000-0000-0000-000000000000", "action": "inspect"}}'
            "]}",
            # Research planner
            '{"queries": [{"query_id": "q1", "query": "Find general background"}]}',
            # Synthesis
            "Based on general background information, the concept is validated.",
        ]
    )

    doc_id = uuid4()
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="bg.txt",
        text="General background data.",
        similarity_score=0.9,
        chunk_index=0,
    )
    fake_retrieval = MagicMock()
    fake_retrieval.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="Find general background",
            retrieval_time=0.01,
            total_matches=1,
            retrieved_chunks=[chunk],
        )
    )

    fake_doc_repo = MagicMock()
    fake_doc_repo.get_by_id = AsyncMock(return_value=None)  # Document not found

    planner = ResearchPlanner(llm_provider=fake_llm, enable_llm_planner=True)
    research_agent = ResearchAgent(retrieval_service=fake_retrieval, planner=planner)
    doc_agent = DocumentAgent(document_repo=fake_doc_repo)
    analysis_agent = AnalysisAgent()

    engine = AgentExecutionEngine(
        specialist_agents=[research_agent, doc_agent, analysis_agent],
        observability=obs,
    )
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    evaluator = ResultEvaluator()

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        result_evaluator=evaluator,
        observability=obs,
        max_plan_iterations=1,
    )

    context = make_context(request_id="req-scen-4", doc_ids=[doc_id])
    resp = await master.execute_request("Analyze document and background", context)

    assert "validated" in resp.answer
    assert "d1" in resp.diagnostics.failed_tasks

    trace = obs.get_trace("req-scen-4")
    assert trace is not None
    assert trace.quality_metrics.successful_task_count == 1
    assert trace.quality_metrics.failed_task_count == 1


@pytest.mark.asyncio
async def test_integration_scenario_5_capability_routing_rejection():
    """Scenario 5: Capability unavailable routes to failure without specialist execution."""
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)

    # Empty capability registry
    empty_registry = CapabilityRegistry()

    router = TaskRouter(registry=empty_registry, observability=obs)
    engine = AgentExecutionEngine(
        specialist_agents=[AnalysisAgent()],
        capability_registry=empty_registry,
        task_router=router,
        observability=obs,
    )

    plan = ExecutionPlan(
        request_id="req-scen-5",
        tasks=[
            AgentTask(
                task_id="t1",
                agent_type=AgentType.ANALYSIS,
                request="Calculate 1+1",
            )
        ],
    )
    context = make_context(request_id="req-scen-5")
    obs.start_trace(request_id=context.request_id)

    outcome = await engine.execute(plan, context)
    assert len(outcome.failed_results) == 1
    assert (
        outcome.failed_results[0].failure_reason
        == AgentFailureReason.CAPABILITY_UNAVAILABLE
    )

    trace = obs.complete_trace(request_id=context.request_id)
    assert trace is not None
    assert len(trace.errors) == 1
    assert trace.errors[0].failure_category == FailureCategory.CAPABILITY_UNAVAILABLE
