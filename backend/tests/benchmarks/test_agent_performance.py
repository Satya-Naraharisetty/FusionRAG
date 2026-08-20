import asyncio
import sys
import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.chat.domain.models import Usage
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
    ExecutionPlan,
)
from app.chat.services.multi_agent.analysis_agent import AnalysisAgent
from app.chat.services.multi_agent.capability_registry import (
    create_default_capability_registry,
)
from app.chat.services.multi_agent.execution_engine import AgentExecutionEngine
from app.chat.services.multi_agent.observability import (
    AgentObservabilityService,
    InMemoryTelemetrySink,
)
from app.chat.services.multi_agent.research_planner import ResearchPlanner
from app.chat.services.multi_agent.task_router import TaskRouter


class FakeBenchmarkLLM:
    def __init__(self) -> None:
        pass

    async def generate(self, messages, model, temperature, max_tokens, **kwargs):
        from app.chat.domain.interfaces import ProviderResponse

        return ProviderResponse(
            content='{"tasks": [{"task_id": "r1", "agent_type": "RESEARCH", "request": "Benchmark query", "dependencies": []}]}',
            usage=Usage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )


def make_bench_context(request_id: str = "bench-req-1") -> AgentExecutionContext:
    return AgentExecutionContext(
        request_id=request_id,
        user_id=uuid4(),
        conversation_id=uuid4(),
        include_library_documents=False,
        include_conversation_documents=True,
        document_ids=[uuid4()],
    )


@pytest.mark.asyncio
async def test_benchmark_sequential_vs_parallel_execution():
    """Benchmark: Compares sequential execution against parallel specialist execution."""
    sink = InMemoryTelemetrySink()
    obs = AgentObservabilityService(sink=sink, enabled=True)

    # Specialist with synthetic 50ms work
    mock_specialist = MagicMock()
    mock_specialist.agent_type = AgentType.RESEARCH

    async def sim_work(task, context):
        await asyncio.sleep(0.05)
        return AgentResult(
            task_id=task.task_id,
            agent_type=AgentType.RESEARCH,
            status=AgentTaskStatus.COMPLETED,
            success=True,
            output="Result data",
            execution_time_ms=50.0,
        )

    mock_specialist.execute_task = AsyncMock(side_effect=sim_work)

    engine = AgentExecutionEngine(
        specialist_agents=[mock_specialist, AnalysisAgent()],
        observability=obs,
    )

    # Parallel plan: 3 independent tasks
    parallel_plan = ExecutionPlan(
        request_id="bench-parallel",
        tasks=[
            AgentTask(task_id="p1", agent_type=AgentType.RESEARCH, request="Q1"),
            AgentTask(task_id="p2", agent_type=AgentType.RESEARCH, request="Q2"),
            AgentTask(task_id="p3", agent_type=AgentType.RESEARCH, request="Q3"),
        ],
    )
    ctx_par = make_bench_context("bench-parallel")
    obs.start_trace(ctx_par.request_id)
    t0 = time.perf_counter()
    _ = await engine.execute(parallel_plan, ctx_par)
    par_time_ms = (time.perf_counter() - t0) * 1000.0

    trace_par = obs.complete_trace(ctx_par.request_id)
    assert trace_par is not None
    assert len(trace_par.batches) == 1
    # Concurrency savings should be positive
    assert trace_par.batches[0].actual_concurrency_savings_ms > 0
    # Wall clock for 3 parallel 50ms tasks should be significantly less than 150ms sequential
    assert par_time_ms < 140.0


@pytest.mark.asyncio
async def test_benchmark_routing_and_decomposition_overhead():
    """Benchmark: Measures TaskRouter and ResearchPlanner decomposition overhead."""
    registry = create_default_capability_registry()
    fake_llm = FakeBenchmarkLLM()
    router = TaskRouter(registry=registry)
    planner = ResearchPlanner(llm_provider=fake_llm, enable_llm_planner=False)

    ctx = make_bench_context("bench-overhead")
    task = AgentTask(
        task_id="t1",
        agent_type=AgentType.RESEARCH,
        request="Compare Q1 revenue vs Q2 revenue",
    )

    # 1. Routing overhead
    t_start = time.perf_counter()
    for _ in range(20):
        decision = await router.route(task, ctx)
        assert decision.selected_capability_id is not None
    routing_avg_ms = ((time.perf_counter() - t_start) / 20.0) * 1000.0
    assert routing_avg_ms < 5.0  # Deterministic routing should be sub-millisecond

    # 2. Heuristic Decomposition overhead
    t_start = time.perf_counter()
    for _ in range(20):
        rplan = await planner.create_plan(
            request_id=ctx.request_id,
            query="Compare Q1 revenue vs Q2 revenue",
            context=ctx,
        )
        assert len(rplan.queries) >= 1
    decomp_avg_ms = ((time.perf_counter() - t_start) / 20.0) * 1000.0
    assert decomp_avg_ms < 5.0


def test_benchmark_memory_overhead_of_request_traces():
    """Benchmark: Measures memory consumption of in-memory trace objects."""
    sink = InMemoryTelemetrySink(max_traces=500)
    obs = AgentObservabilityService(sink=sink, enabled=True)

    traces = []
    for i in range(100):
        req_id = f"bench-mem-{i}"
        _ = obs.start_trace(
            request_id=req_id,
            conversation_id="conv-1",
            user_id=uuid4(),
            metadata={"index": i},
        )
        for t_idx in range(5):
            obs.start_task(
                request_id=req_id,
                task_id=f"task_{t_idx}",
                agent_type="RESEARCH",
                estimated_latency_ms=100.0,
            )
            obs.complete_task(
                request_id=req_id,
                task_id=f"task_{t_idx}",
                actual_latency_ms=90.0,
                evidence_count=2,
            )
        completed = obs.complete_trace(req_id)
        if completed:
            traces.append(completed)

    assert len(traces) == 100
    # Approximate memory size check: 100 traces should comfortably be under 2MB
    total_bytes = sum(sys.getsizeof(t) for t in traces)
    assert total_bytes < 2_000_000
