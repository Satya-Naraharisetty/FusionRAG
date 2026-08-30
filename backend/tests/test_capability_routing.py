from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.chat.domain.models import Usage
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentFailureReason,
    AgentTask,
    AgentType,
    CapabilityDescriptor,
    CapabilityRequirement,
    CapabilityType,
    ExecutionPlan,
)
from app.chat.services.multi_agent.analysis_agent import AnalysisAgent
from app.chat.services.multi_agent.capability_registry import (
    CapabilityRegistry,
    create_default_capability_registry,
)
from app.chat.services.multi_agent.execution_engine import (
    AgentExecutionEngine,
)
from app.chat.services.multi_agent.master_agent import MasterAgent
from app.chat.services.multi_agent.research_agent import ResearchAgent
from app.chat.services.multi_agent.research_planner import ResearchPlanner
from app.chat.services.multi_agent.result_evaluator import ResultEvaluator
from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent
from app.chat.services.multi_agent.task_router import TaskRouter
from app.documents.domain.models import (
    Chunk,
    Document,
    RetrievedChunk,
    SearchResult,
)

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
            else "Synthesized answer based on evidence."
        )
        from app.chat.domain.interfaces import ProviderResponse

        return ProviderResponse(
            content=content,
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )

    async def stream(self, messages, model, temperature, max_tokens, **kwargs):
        self.call_history.append(messages)
        tokens = ["Synthesized", " answer", " stream."]
        for tok in tokens:
            from app.chat.domain.interfaces import StreamChunk

            yield StreamChunk(text_delta=tok, usage=None)
        from app.chat.domain.interfaces import StreamChunk

        yield StreamChunk(
            text_delta="",
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


class FakeDocumentRepo:
    def __init__(self, documents: dict[UUID, Document] | None = None) -> None:
        self.documents = dict(documents or {})

    async def get_by_id(self, id: UUID) -> Document | None:
        return self.documents.get(id)

    async def list_by_user(self, user_id: UUID) -> list[Document]:
        return [d for d in self.documents.values() if d.user_id == user_id]

    async def list_by_conversation(
        self, conversation_id: UUID, user_id: UUID
    ) -> list[Document]:
        return [
            d
            for d in self.documents.values()
            if d.user_id == user_id and d.conversation_id == conversation_id
        ]


class FakeChunkRepo:
    def __init__(self, chunks: dict[UUID, list[Chunk]] | None = None) -> None:
        self.chunks = dict(chunks or {})

    async def get_chunks_by_document_id(self, document_id: UUID) -> list[Chunk]:
        return self.chunks.get(document_id, [])

    async def get_by_id(self, chunk_id: UUID) -> Chunk | None:
        for chunk_list in self.chunks.values():
            for c in chunk_list:
                if c.id == chunk_id:
                    return c
        return None


def create_mock_retrieved_chunk(
    content: str = "Evidence content",
    doc_name: str = "doc.txt",
    score: float = 0.9,
    doc_id: UUID | None = None,
    chunk_id: UUID | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id or uuid4(),
        document_id=doc_id or uuid4(),
        document_name=doc_name,
        text=content,
        similarity_score=score,
        chunk_index=0,
    )


def create_fake_retrieval_service(
    chunks: list[RetrievedChunk] | None = None,
) -> AsyncMock:
    mock_retrieval = AsyncMock()
    chunks_to_return = chunks or [create_mock_retrieved_chunk()]

    async def mock_retrieve(query: str, user_id, top_k=5, retrieval_scope=None):
        return SearchResult(
            original_query=query,
            retrieved_chunks=chunks_to_return,
            total_matches=len(chunks_to_return),
            retrieval_time=10.0,
        )

    mock_retrieval.retrieve = AsyncMock(side_effect=mock_retrieve)
    return mock_retrieval


# ---------------------------------------------------------------------------
# Test Category A: Capability Registry
# ---------------------------------------------------------------------------


def test_registry_default_capabilities() -> None:
    registry = create_default_capability_registry()
    research = registry.get("research.fusion_rag")
    doc = registry.get("document.inspection")
    analysis = registry.get("analysis.safe_calculator")
    synthesis = registry.get("synthesis.grounded_summary")

    assert research is not None
    assert research.capability_type == CapabilityType.RESEARCH
    assert "semantic_search" in research.supported_operations

    assert doc is not None
    assert doc.capability_type == CapabilityType.DOCUMENT_INSPECTION

    assert analysis is not None
    assert analysis.capability_type == CapabilityType.ANALYSIS

    assert synthesis is not None
    assert synthesis.capability_type == CapabilityType.SYNTHESIS


def test_registry_custom_registration_and_unregistration() -> None:
    registry = CapabilityRegistry()
    desc = CapabilityDescriptor(
        capability_id="custom.test",
        capability_type=CapabilityType.RESEARCH,
        description="Custom test capability",
        supported_operations=["test_op"],
        required_context=["user_id"],
        estimated_latency_ms=100.0,
        estimated_cost_units=0.1,
    )
    registry.register(desc)
    assert registry.get("custom.test") == desc
    assert len(registry.list_enabled()) == 1

    removed = registry.unregister("custom.test")
    assert removed is True
    assert registry.get("custom.test") is None


def test_registry_disabled_capability_filtering() -> None:
    registry = CapabilityRegistry()
    desc = CapabilityDescriptor(
        capability_id="disabled.test",
        capability_type=CapabilityType.ANALYSIS,
        description="Disabled capability",
        enabled=False,
    )
    registry.register(desc)

    assert registry.get("disabled.test") is not None
    assert len(registry.list_enabled()) == 0
    assert len(registry.list_by_type(CapabilityType.ANALYSIS)) == 0


def test_registry_invalid_descriptor_rejection() -> None:
    registry = CapabilityRegistry()
    invalid_desc = CapabilityDescriptor(
        capability_id="",  # Empty ID
        capability_type=CapabilityType.RESEARCH,
        description="Invalid descriptor",
    )
    with pytest.raises(ValueError, match="Capability ID must not be empty"):
        registry.register(invalid_desc)


# ---------------------------------------------------------------------------
# Test Category B: Deterministic Routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deterministic_routing_research_task() -> None:
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(
        request_id="req-1",
        user_id=uuid4(),
    )
    task = AgentTask(
        task_id="task-1",
        request="What are the company leave policies?",
        agent_type=AgentType.RESEARCH,
        parameters={"operation": "semantic_search"},
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id == "research.fusion_rag"
    assert decision.capability_type == CapabilityType.RESEARCH
    assert decision.reason_code == "EXACT_CAPABILITY_MATCH"
    assert decision.confidence == 1.0
    assert decision.estimated_latency_ms == 1200.0
    assert decision.estimated_cost_units == 1.0


@pytest.mark.asyncio
async def test_deterministic_routing_document_task() -> None:
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(
        request_id="req-2",
        user_id=uuid4(),
    )
    task = AgentTask(
        task_id="task-2",
        request="Inspect document 123",
        agent_type=AgentType.DOCUMENT,
        parameters={"action": "inspect"},
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id == "document.inspection"
    assert decision.capability_type == CapabilityType.DOCUMENT_INSPECTION
    assert decision.reason_code == "EXACT_CAPABILITY_MATCH"


@pytest.mark.asyncio
async def test_deterministic_routing_analysis_task() -> None:
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(
        request_id="req-3",
        user_id=uuid4(),
    )
    task = AgentTask(
        task_id="task-3",
        request="Calculate 100 * 1.15",
        agent_type=AgentType.ANALYSIS,
        parameters={"action": "calculate"},
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id == "analysis.safe_calculator"
    assert decision.capability_type == CapabilityType.ANALYSIS
    assert decision.reason_code == "EXACT_CAPABILITY_MATCH"


@pytest.mark.asyncio
async def test_routing_missing_required_context() -> None:
    registry = CapabilityRegistry(
        [
            CapabilityDescriptor(
                capability_id="doc.needs_doc_ids",
                capability_type=CapabilityType.DOCUMENT_INSPECTION,
                description="Requires explicit document_ids in context",
                required_context=["document_ids"],
            )
        ]
    )
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(
        request_id="req-4",
        user_id=uuid4(),
        document_ids=None,  # Missing document_ids
    )
    task = AgentTask(
        task_id="task-4",
        request="Inspect docs",
        agent_type=AgentType.DOCUMENT,
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id is None
    assert decision.reason_code == "CONTEXT_MISSING"
    assert decision.rejected_capabilities["doc.needs_doc_ids"] == "CONTEXT_MISSING"


@pytest.mark.asyncio
async def test_routing_disabled_capability_rejection() -> None:
    registry = CapabilityRegistry(
        [
            CapabilityDescriptor(
                capability_id="research.disabled",
                capability_type=CapabilityType.RESEARCH,
                description="Disabled research",
                enabled=False,
            )
        ]
    )
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(request_id="req-5", user_id=uuid4())
    task = AgentTask(
        task_id="task-5",
        request="Search facts",
        agent_type=AgentType.RESEARCH,
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id is None
    assert decision.reason_code == "CAPABILITY_DISABLED"


@pytest.mark.asyncio
async def test_routing_reproducible_and_deterministic() -> None:
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(request_id="req-6", user_id=uuid4())
    task = AgentTask(
        task_id="task-6",
        request="Compute annual sum",
        agent_type=AgentType.ANALYSIS,
    )

    decisions = [await router.route(task, context) for _ in range(5)]
    first_dec = decisions[0]
    for d in decisions[1:]:
        assert d.selected_capability_id == first_dec.selected_capability_id
        assert d.reason_code == first_dec.reason_code
        assert d.estimated_latency_ms == first_dec.estimated_latency_ms


# ---------------------------------------------------------------------------
# Test Category C: Budget Routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_routing_task_latency_budget_exceeded() -> None:
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(request_id="req-7", user_id=uuid4())
    # research.fusion_rag has estimated latency 1200ms
    task = AgentTask(
        task_id="task-7",
        request="Quick search",
        agent_type=AgentType.RESEARCH,
        max_latency_ms=500.0,  # Below 1200ms
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id is None
    assert decision.reason_code == "BUDGET_EXCEEDED"
    assert decision.rejected_capabilities["research.fusion_rag"] == "BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_budget_routing_task_cost_budget_exceeded() -> None:
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(request_id="req-8", user_id=uuid4())
    # research.fusion_rag has estimated cost 1.0 unit
    task = AgentTask(
        task_id="task-8",
        request="Low cost search",
        agent_type=AgentType.RESEARCH,
        max_cost_units=0.5,  # Below 1.0
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id is None
    assert decision.reason_code == "BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_budget_routing_remaining_request_budget_exceeded() -> None:
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(request_id="req-9", user_id=uuid4())
    task = AgentTask(
        task_id="task-9",
        request="Search facts",
        agent_type=AgentType.RESEARCH,
    )

    # Remaining request budget has only 0.2 cost units left
    decision = await router.route(task, context, remaining_cost_units=0.2)
    assert decision.selected_capability_id is None
    assert decision.reason_code == "BUDGET_EXCEEDED"


# ---------------------------------------------------------------------------
# Test Category D: Security & Isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_arbitrary_capability_id_rejected() -> None:
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(request_id="req-10", user_id=uuid4())
    task = AgentTask(
        task_id="task-10",
        request="Arbitrary system call",
        agent_type=AgentType.RESEARCH,
        preferred_capability="system.arbitrary_executor",
    )

    decision = await router.route(task, context)
    # The unregistered preferred capability is rejected, falling back to eligible research capability
    assert "system.arbitrary_executor" in decision.rejected_capabilities
    assert decision.selected_capability_id == "research.fusion_rag"


@pytest.mark.asyncio
async def test_security_synthesis_rejected_as_executable_task() -> None:
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(request_id="req-11", user_id=uuid4())
    task = AgentTask(
        task_id="task-11",
        request="Synthesize early",
        agent_type=AgentType.SYNTHESIS,
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id is None
    assert decision.reason_code == "POLICY_REJECTED"


@pytest.mark.asyncio
async def test_security_cross_class_capability_contradiction_rejected() -> None:
    registry = create_default_capability_registry()
    router = TaskRouter(registry=registry)
    context = AgentExecutionContext(request_id="req-12", user_id=uuid4())
    task = AgentTask(
        task_id="task-12",
        request="Research with analysis capability requirement",
        agent_type=AgentType.RESEARCH,
        capability_requirements=[
            CapabilityRequirement(capability_type=CapabilityType.ANALYSIS)
        ],
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id is None
    assert decision.reason_code == "CAPABILITY_MISMATCH"


# ---------------------------------------------------------------------------
# Test Category E: Execution Engine Integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execution_engine_routing_and_metadata_recording() -> None:
    mock_retrieval = create_fake_retrieval_service(
        [
            create_mock_retrieved_chunk(
                content="Evidence chunk 1", doc_name="doc1.txt", score=0.9
            )
        ]
    )
    fake_llm = FakeLLMProvider()
    research_agent = ResearchAgent(
        retrieval_service=mock_retrieval, llm_provider=fake_llm
    )
    analysis_agent = AnalysisAgent()

    engine = AgentExecutionEngine(
        specialist_agents=[research_agent, analysis_agent],
    )

    plan = ExecutionPlan(
        request_id="req-13",
        tasks=[
            AgentTask(
                task_id="t1",
                request="Search policy",
                agent_type=AgentType.RESEARCH,
                parameters={"query": "policy"},
            ),
            AgentTask(
                task_id="t2",
                request="Calculate 10 + 20",
                agent_type=AgentType.ANALYSIS,
                parameters={"expression": "10 + 20"},
                dependencies=["t1"],
            ),
        ],
    )

    context = AgentExecutionContext(request_id="req-13", user_id=uuid4())
    outcome = await engine.execute(plan, context)

    assert len(outcome.completed_results) == 2
    assert len(outcome.failed_results) == 0

    res_map = {r.task_id: r for r in outcome.completed_results}
    assert res_map["t1"].metadata.get("routed_capability") == "research.fusion_rag"
    assert res_map["t1"].metadata.get("routing_reason_code") == "EXACT_CAPABILITY_MATCH"
    assert res_map["t2"].metadata.get("routed_capability") == "analysis.safe_calculator"


@pytest.mark.asyncio
async def test_execution_engine_no_capability_failure_isolation() -> None:
    registry = CapabilityRegistry(
        [
            CapabilityDescriptor(
                capability_id="research.fusion_rag",
                capability_type=CapabilityType.RESEARCH,
                description="Disabled research",
                enabled=False,
            ),
            CapabilityDescriptor(
                capability_id="analysis.safe_calculator",
                capability_type=CapabilityType.ANALYSIS,
                description="Calculator",
                enabled=True,
            ),
        ]
    )
    router = TaskRouter(registry=registry)
    mock_retrieval = create_fake_retrieval_service()
    research_agent = ResearchAgent(retrieval_service=mock_retrieval)
    analysis_agent = AnalysisAgent()

    engine = AgentExecutionEngine(
        specialist_agents=[research_agent, analysis_agent],
        task_router=router,
        capability_registry=registry,
    )

    plan = ExecutionPlan(
        request_id="req-14",
        tasks=[
            AgentTask(
                task_id="unrouted_1",
                request="Find policy",
                agent_type=AgentType.RESEARCH,
            ),
            AgentTask(
                task_id="calc_1",
                request="1 + 1",
                agent_type=AgentType.ANALYSIS,
                parameters={"expression": "1 + 1"},
                dependencies=[],
            ),
        ],
    )

    context = AgentExecutionContext(request_id="req-14", user_id=uuid4())
    outcome = await engine.execute(plan, context)

    assert len(outcome.completed_results) == 1
    assert outcome.completed_results[0].task_id == "calc_1"

    assert len(outcome.failed_results) == 1
    failed = outcome.failed_results[0]
    assert failed.task_id == "unrouted_1"
    assert failed.failure_reason == AgentFailureReason.CAPABILITY_UNAVAILABLE


@pytest.mark.asyncio
async def test_execution_engine_concurrent_routed_execution() -> None:
    analysis_agent = AnalysisAgent()
    engine = AgentExecutionEngine(
        specialist_agents=[analysis_agent],
    )

    plan = ExecutionPlan(
        request_id="req-15",
        tasks=[
            AgentTask(
                task_id="c1",
                request="10 * 2",
                agent_type=AgentType.ANALYSIS,
                parameters={"expression": "10 * 2"},
            ),
            AgentTask(
                task_id="c2",
                request="20 * 3",
                agent_type=AgentType.ANALYSIS,
                parameters={"expression": "20 * 3"},
            ),
        ],
    )

    context = AgentExecutionContext(request_id="req-15", user_id=uuid4())
    outcome = await engine.execute(plan, context)

    assert len(outcome.completed_results) == 2
    assert outcome.total_calls == 2


# ---------------------------------------------------------------------------
# Test Category F: Prompt 3.2 Replanning Integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replanning_routes_through_task_router() -> None:
    mock_retrieval = create_fake_retrieval_service(
        [
            create_mock_retrieved_chunk(
                content="Q3 Revenue was 5M.", doc_name="doc.txt", score=0.9
            )
        ]
    )
    fake_llm = FakeLLMProvider()
    research_agent = ResearchAgent(
        retrieval_service=mock_retrieval, llm_provider=fake_llm
    )
    analysis_agent = AnalysisAgent()
    synthesis_agent = SynthesisAgent(llm_provider=fake_llm)

    engine = AgentExecutionEngine(specialist_agents=[research_agent, analysis_agent])
    evaluator = ResultEvaluator(llm_provider=fake_llm)
    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis_agent,
        result_evaluator=evaluator,
        max_plan_iterations=2,
    )

    context = AgentExecutionContext(request_id="req-16", user_id=uuid4())
    response = await master.execute_request("What was the revenue and growth?", context)

    assert response.answer is not None
    assert response.diagnostics.routing_decisions >= 1
    assert response.diagnostics.estimated_cost_units > 0


# ---------------------------------------------------------------------------
# Test Category G: Prompt 3.3 Research Planner Integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routed_research_agent_invokes_research_planner() -> None:
    mock_retrieval = create_fake_retrieval_service(
        [
            create_mock_retrieved_chunk(
                content="Compound query evidence.", doc_name="report.pdf", score=0.95
            )
        ]
    )
    fake_llm = FakeLLMProvider()
    planner = ResearchPlanner(llm_provider=fake_llm, enable_llm_planner=False)
    research_agent = ResearchAgent(
        retrieval_service=mock_retrieval,
        planner=planner,
        llm_provider=fake_llm,
    )
    engine = AgentExecutionEngine(specialist_agents=[research_agent])

    plan = ExecutionPlan(
        request_id="req-17",
        tasks=[
            AgentTask(
                task_id="r1",
                request="Compare Q1 vs Q2 earnings",
                agent_type=AgentType.RESEARCH,
                parameters={"query": "Compare Q1 vs Q2 earnings"},
            )
        ],
    )
    context = AgentExecutionContext(request_id="req-17", user_id=uuid4())
    outcome = await engine.execute(plan, context)

    assert len(outcome.completed_results) == 1
    res = outcome.completed_results[0]
    assert res.agent_type == AgentType.RESEARCH
    assert "research_plan" in res.metadata
    assert res.metadata["research_plan"]["strategy"] == "multi_period_decomposition"


# ---------------------------------------------------------------------------
# Test Category H: LLM Advisory Router
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_advisory_router_valid_recommendation() -> None:
    fake_llm = FakeLLMProvider(['{"capability_id": "research.fusion_rag"}'])
    registry = create_default_capability_registry()
    router = TaskRouter(
        registry=registry,
        llm_provider=fake_llm,
        enable_llm_router=True,
    )

    context = AgentExecutionContext(request_id="req-18", user_id=uuid4())
    task = AgentTask(
        task_id="task-18",
        request="Deep search into policy guidelines",
        agent_type=AgentType.RESEARCH,
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id == "research.fusion_rag"


@pytest.mark.asyncio
async def test_llm_advisory_router_invalid_output_falls_back() -> None:
    fake_llm = FakeLLMProvider(["invalid non json response from model"])
    registry = create_default_capability_registry()
    router = TaskRouter(
        registry=registry,
        llm_provider=fake_llm,
        enable_llm_router=True,
    )

    context = AgentExecutionContext(request_id="req-19", user_id=uuid4())
    task = AgentTask(
        task_id="task-19",
        request="Calculate revenue",
        agent_type=AgentType.ANALYSIS,
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id == "analysis.safe_calculator"


@pytest.mark.asyncio
async def test_llm_advisory_router_unregistered_recommendation_rejected() -> None:
    fake_llm = FakeLLMProvider(
        ['{"capability_id": "malicious.unregistered_capability"}']
    )
    registry = create_default_capability_registry()
    router = TaskRouter(
        registry=registry,
        llm_provider=fake_llm,
        enable_llm_router=True,
    )

    context = AgentExecutionContext(request_id="req-20", user_id=uuid4())
    task = AgentTask(
        task_id="task-20",
        request="Search query",
        agent_type=AgentType.RESEARCH,
    )

    decision = await router.route(task, context)
    assert decision.selected_capability_id == "research.fusion_rag"


# ---------------------------------------------------------------------------
# Test Category I: Streaming Lifecycle Events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_lifecycle_events() -> None:
    mock_retrieval = create_fake_retrieval_service()
    fake_llm = FakeLLMProvider()
    research_agent = ResearchAgent(
        retrieval_service=mock_retrieval, llm_provider=fake_llm
    )
    analysis_agent = AnalysisAgent()
    synthesis_agent = SynthesisAgent(llm_provider=fake_llm)

    engine = AgentExecutionEngine(specialist_agents=[research_agent, analysis_agent])
    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis_agent,
    )

    context = AgentExecutionContext(request_id="req-21", user_id=uuid4())
    events: list[dict[str, Any]] = []

    async for ev in master.execute_request_stream("5 + 5", context):
        events.append(ev)

    event_names = [e["event"] for e in events]
    assert "capability_routing_started" in event_names
    assert "capability_routing_completed" in event_names
    assert "text" in event_names
    assert "synthesis_done" in event_names

    # Verify no internal prompt or chain-of-thought is leaked in routing events
    routing_events = [e for e in events if e["event"].startswith("capability_routing_")]
    for r_ev in routing_events:
        data = r_ev.get("data", {})
        assert "prompt" not in data
        assert "chain_of_thought" not in data
        assert "api_key" not in data
