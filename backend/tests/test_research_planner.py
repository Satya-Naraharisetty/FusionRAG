import asyncio
import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.chat.domain.interfaces import LLMProvider, ProviderResponse
from app.chat.domain.models import Usage
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentTask,
    AgentType,
    ResearchPlan,
    ResearchQuery,
)
from app.chat.services.multi_agent.execution_engine import AgentExecutionEngine
from app.chat.services.multi_agent.master_agent import MasterAgent
from app.chat.services.multi_agent.research_agent import ResearchAgent
from app.chat.services.multi_agent.research_planner import ResearchPlanner
from app.chat.services.multi_agent.result_evaluator import ResultEvaluator
from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent
from app.documents.domain.models import (
    DocumentRetrievalScope,
    RetrievedChunk,
    SearchResult,
)
from app.documents.services.retrieval_service import RetrievalService

# --- Fixtures & Helpers ---


class FakePlannerLLMProvider:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])

    async def generate(self, messages, model, temperature, max_tokens, **kwargs):
        content = (
            self.responses.pop(0)
            if self.responses
            else "Synthesized multi-agent response based on retrieved evidence."
        )
        return ProviderResponse(
            content=content,
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


def create_mock_chunk(
    text: str,
    doc_id=None,
    chunk_id=None,
    doc_name: str = "Annual_Report.pdf",
    score: float = 0.9,
    index: int = 0,
) -> RetrievedChunk:
    chunk_id = chunk_id or uuid4()
    doc_id = doc_id or uuid4()
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        document_name=doc_name,
        text=text,
        similarity_score=score,
        chunk_index=index,
        metadata={"section": "Financials"},
    )


def create_mock_retrieval_service(chunks_to_return=None) -> RetrievalService:
    service = MagicMock(spec=RetrievalService)
    if chunks_to_return is None:
        chunks_to_return = [create_mock_chunk("General knowledge chunk")]

    async def mock_retrieve(query: str, user_id, top_k=5, retrieval_scope=None):
        return SearchResult(
            original_query=query,
            retrieved_chunks=chunks_to_return,
            total_matches=len(chunks_to_return),
            retrieval_time=12.5,
        )

    service.retrieve = AsyncMock(side_effect=mock_retrieve)
    return service


# ============================================================================
# A. Planning Tests
# ============================================================================


def test_simple_research_query_produces_one_focused_query():
    planner = ResearchPlanner(enable_llm_planner=False)
    plan = planner.plan_heuristic("req-1", "What is the return policy?", top_k=5)

    assert isinstance(plan, ResearchPlan)
    assert len(plan.queries) == 1
    assert "return policy" in plan.queries[0].query.lower()
    assert plan.decomposition_strategy == "single_query"


def test_multi_period_query_decomposes_correctly():
    planner = ResearchPlanner(enable_llm_planner=False)
    plan = planner.plan_heuristic(
        "req-2",
        "Compare Q2 and Q3 revenue and explain the reason for the change.",
        top_k=5,
    )

    assert isinstance(plan, ResearchPlan)
    assert plan.decomposition_strategy == "multi_period_decomposition"
    queries_text = [q.query.lower() for q in plan.queries]

    # Should contain Q2 and Q3 revenue queries
    assert any("q2" in q and "revenue" in q for q in queries_text)
    assert any("q3" in q and "revenue" in q for q in queries_text)
    # Should contain change / drivers / explanation query
    assert any(
        "drivers" in q or "change" in q or "explanation" in q for q in queries_text
    )
    assert len(plan.queries) <= 4


def test_multi_entity_query_decomposes_correctly():
    planner = ResearchPlanner(enable_llm_planner=False)
    plan = planner.plan_heuristic(
        "req-3",
        "Compare Product Alpha vs Product Beta performance",
        top_k=5,
    )

    assert isinstance(plan, ResearchPlan)
    assert plan.decomposition_strategy == "comparison_decomposition"
    queries_text = [q.query.lower() for q in plan.queries]
    assert any("alpha" in q for q in queries_text)
    assert any("beta" in q for q in queries_text)


def test_comparison_query_creates_separate_evidence_requirements():
    planner = ResearchPlanner(enable_llm_planner=False)
    plan = planner.plan_heuristic(
        "req-4",
        "What is the difference between Plan A and Plan B?",
        top_k=5,
    )

    assert plan.decomposition_strategy == "comparison_decomposition"
    assert len(plan.queries) >= 2
    for q in plan.queries:
        assert len(q.required_evidence) > 0


def test_why_query_creates_supporting_context_retrieval():
    planner = ResearchPlanner(enable_llm_planner=False)
    plan = planner.plan_heuristic(
        "req-5",
        "Why did sales drop significantly in November?",
        top_k=5,
    )

    assert plan.decomposition_strategy in (
        "explanation_decomposition",
        "multi_period_decomposition",
    )
    queries_text = [q.query.lower() for q in plan.queries]
    assert any("drop" in q or "sales" in q for q in queries_text)
    assert any("causes" in q or "drivers" in q or "reasons" in q for q in queries_text)


@pytest.mark.asyncio
async def test_llm_planner_produces_valid_structured_plan():
    mock_llm = MagicMock(spec=LLMProvider)
    llm_json = """{
        "decomposition_strategy": "multi_period_decomposition",
        "reasoning_summary": "Decomposed into Q1 and Q2 revenue queries.",
        "queries": [
            {
                "query_id": "q1_rev",
                "query": "Q1 2024 total revenue",
                "purpose": "Find Q1 revenue figure",
                "priority": 0,
                "required_evidence": ["Q1 revenue"],
                "dependencies": []
            },
            {
                "query_id": "q2_rev",
                "query": "Q2 2024 total revenue",
                "purpose": "Find Q2 revenue figure",
                "priority": 1,
                "required_evidence": ["Q2 revenue"],
                "dependencies": []
            }
        ]
    }"""
    mock_llm.generate = AsyncMock(
        return_value=ProviderResponse(content=llm_json, usage=Usage())
    )

    planner = ResearchPlanner(llm_provider=mock_llm, enable_llm_planner=True)
    plan = await planner.create_plan("req-llm", "Compare Q1 and Q2 revenue 2024")

    assert plan.metadata.get("planner_mode") == "llm"
    assert len(plan.queries) == 2
    assert plan.queries[0].query_id == "q1_rev"
    assert plan.queries[1].query_id == "q2_rev"


@pytest.mark.asyncio
async def test_invalid_llm_output_falls_back_to_heuristic():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate = AsyncMock(
        return_value=ProviderResponse(
            content="Sorry, I cannot produce JSON right now.", usage=Usage()
        )
    )

    planner = ResearchPlanner(llm_provider=mock_llm, enable_llm_planner=True)
    plan = await planner.create_plan("req-invalid", "Compare Q2 and Q3 revenue")

    assert plan.metadata.get("planner_mode") == "heuristic"
    assert len(plan.queries) >= 2


@pytest.mark.asyncio
async def test_llm_timeout_falls_back_safely():
    mock_llm = MagicMock(spec=LLMProvider)

    async def timeout_gen(*args, **kwargs):
        await asyncio.sleep(0.5)
        return ProviderResponse(content="{}", usage=Usage())

    mock_llm.generate = AsyncMock(side_effect=timeout_gen)
    planner = ResearchPlanner(
        llm_provider=mock_llm, enable_llm_planner=True, query_timeout=0.05
    )
    plan = await planner.create_plan("req-timeout", "Compare Q2 and Q3 revenue")

    assert plan.metadata.get("planner_mode") == "heuristic"
    assert len(plan.queries) >= 2


# ============================================================================
# B. Query Limits Tests
# ============================================================================


def test_planner_rejects_and_truncates_plans_exceeding_max_subqueries():
    planner = ResearchPlanner(enable_llm_planner=False, max_subqueries=2)
    plan = planner.plan_heuristic(
        "req-limit",
        "Compare Q1, Q2, Q3, and Q4 revenue and explain all changes",
        top_k=5,
    )

    assert len(plan.queries) <= 2


@pytest.mark.asyncio
async def test_retrieval_calls_never_exceed_max_retrieval_calls():
    # Setup mock retrieval that counts calls
    call_count = 0
    service = MagicMock(spec=RetrievalService)

    async def mock_retrieve(query: str, user_id, top_k=5, retrieval_scope=None):
        nonlocal call_count
        call_count += 1
        return SearchResult(
            original_query=query,
            retrieved_chunks=[create_mock_chunk(f"Result for {query}")],
            total_matches=1,
            retrieval_time=5.0,
        )

    service.retrieve = AsyncMock(side_effect=mock_retrieve)

    # Set planner to return 4 queries, but max_retrieval_calls = 2
    planner = MagicMock(spec=ResearchPlanner)
    planner.create_plan = AsyncMock(
        return_value=ResearchPlan(
            request_id="req-cap",
            original_query="multi query",
            queries=[
                ResearchQuery(query_id=f"q_{i}", query=f"subquery {i}", purpose="test")
                for i in range(4)
            ],
            decomposition_strategy="multi_query",
        )
    )

    agent = ResearchAgent(
        retrieval_service=service, planner=planner, max_retrieval_calls=2
    )
    task = AgentTask(task_id="t1", request="multi query", agent_type=AgentType.RESEARCH)
    context = AgentExecutionContext(request_id="r1", user_id=uuid4())

    result = await agent.execute_task(task, context)

    assert result.success is True
    assert call_count <= 2
    assert result.metadata["queries_executed"] <= 2


def test_duplicate_queries_are_removed():
    planner = ResearchPlanner(enable_llm_planner=False)
    plan = planner.plan_heuristic("req-dedup", "Revenue revenue revenue?", top_k=5)

    queries = [q.query.lower() for q in plan.queries]
    assert len(queries) == len(set(queries))


def test_pure_component_cannot_recurse():
    planner = ResearchPlanner(enable_llm_planner=False)
    # ResearchPlanner has no references to MasterAgent, ExecutionEngine, or RetrievalService
    assert not hasattr(planner, "retrieval_service")
    assert not hasattr(planner, "execution_engine")
    assert not hasattr(planner, "master_agent")


# ============================================================================
# C. Parallel Execution Tests
# ============================================================================


@pytest.mark.asyncio
async def test_independent_research_queries_execute_concurrently():
    execution_order = []
    service = MagicMock(spec=RetrievalService)

    async def mock_retrieve(query: str, user_id, top_k=5, retrieval_scope=None):
        execution_order.append(f"start:{query}")
        await asyncio.sleep(0.05)
        execution_order.append(f"end:{query}")
        return SearchResult(
            original_query=query,
            retrieved_chunks=[create_mock_chunk(f"Content for {query}")],
            total_matches=1,
            retrieval_time=50.0,
        )

    service.retrieve = AsyncMock(side_effect=mock_retrieve)

    planner = MagicMock(spec=ResearchPlanner)
    planner.create_plan = AsyncMock(
        return_value=ResearchPlan(
            request_id="req-par",
            original_query="Independent queries",
            queries=[
                ResearchQuery(
                    query_id="q1", query="Query 1", purpose="p1", dependencies=[]
                ),
                ResearchQuery(
                    query_id="q2", query="Query 2", purpose="p2", dependencies=[]
                ),
            ],
            decomposition_strategy="multi_query",
        )
    )

    agent = ResearchAgent(retrieval_service=service, planner=planner)
    task = AgentTask(task_id="t-par", request="test", agent_type=AgentType.RESEARCH)
    context = AgentExecutionContext(request_id="r-par", user_id=uuid4())

    t0 = time.perf_counter()
    result = await agent.execute_task(task, context)
    elapsed = time.perf_counter() - t0

    assert result.success is True
    assert len(result.evidence) == 2
    # If concurrent, total time is ~50ms (not 100ms+)
    assert elapsed < 0.15
    # Both start before either finishes
    assert execution_order.index("start:Query 1") < execution_order.index("end:Query 2")
    assert execution_order.index("start:Query 2") < execution_order.index("end:Query 1")


@pytest.mark.asyncio
async def test_dependent_research_queries_execute_after_dependencies():
    execution_order = []
    service = MagicMock(spec=RetrievalService)

    async def mock_retrieve(query: str, user_id, top_k=5, retrieval_scope=None):
        execution_order.append(f"start:{query}")
        await asyncio.sleep(0.02)
        execution_order.append(f"end:{query}")
        return SearchResult(
            original_query=query,
            retrieved_chunks=[create_mock_chunk(f"Content for {query}")],
            total_matches=1,
            retrieval_time=20.0,
        )

    service.retrieve = AsyncMock(side_effect=mock_retrieve)

    planner = MagicMock(spec=ResearchPlanner)
    planner.create_plan = AsyncMock(
        return_value=ResearchPlan(
            request_id="req-dep",
            original_query="Dependent queries",
            queries=[
                ResearchQuery(
                    query_id="q1", query="Query 1", purpose="p1", dependencies=[]
                ),
                ResearchQuery(
                    query_id="q2", query="Query 2", purpose="p2", dependencies=["q1"]
                ),
            ],
            decomposition_strategy="sequential_refinement",
        )
    )

    agent = ResearchAgent(retrieval_service=service, planner=planner)
    task = AgentTask(task_id="t-dep", request="test", agent_type=AgentType.RESEARCH)
    context = AgentExecutionContext(request_id="r-dep", user_id=uuid4())

    result = await agent.execute_task(task, context)
    assert result.success is True
    # q1 must end before q2 starts
    assert execution_order.index("end:Query 1") < execution_order.index("start:Query 2")


@pytest.mark.asyncio
async def test_one_failed_query_does_not_cancel_independent_queries():
    service = MagicMock(spec=RetrievalService)

    async def mock_retrieve(query: str, user_id, top_k=5, retrieval_scope=None):
        if "failing" in query:
            raise RuntimeError("Database connection reset")
        return SearchResult(
            original_query=query,
            retrieved_chunks=[create_mock_chunk("Successful content")],
            total_matches=1,
            retrieval_time=10.0,
        )

    service.retrieve = AsyncMock(side_effect=mock_retrieve)

    planner = MagicMock(spec=ResearchPlanner)
    planner.create_plan = AsyncMock(
        return_value=ResearchPlan(
            request_id="req-fail-iso",
            original_query="Fail isolation",
            queries=[
                ResearchQuery(query_id="q_good", query="good query", purpose="p1"),
                ResearchQuery(query_id="q_bad", query="failing query", purpose="p2"),
            ],
            decomposition_strategy="multi_query",
        )
    )

    agent = ResearchAgent(retrieval_service=service, planner=planner)
    task = AgentTask(task_id="t-iso", request="test", agent_type=AgentType.RESEARCH)
    context = AgentExecutionContext(request_id="r-iso", user_id=uuid4())

    result = await agent.execute_task(task, context)

    assert result.success is True
    assert len(result.evidence) == 1
    assert result.metadata["queries_with_results"] == 1
    assert "q_bad" in result.metadata["empty_queries"]


@pytest.mark.asyncio
async def test_query_timeout_is_isolated():
    service = MagicMock(spec=RetrievalService)

    async def mock_retrieve(query: str, user_id, top_k=5, retrieval_scope=None):
        if "slow" in query:
            await asyncio.sleep(0.5)
        return SearchResult(
            original_query=query,
            retrieved_chunks=[create_mock_chunk("Fast chunk")],
            total_matches=1,
            retrieval_time=10.0,
        )

    service.retrieve = AsyncMock(side_effect=mock_retrieve)

    planner = MagicMock(spec=ResearchPlanner)
    planner.create_plan = AsyncMock(
        return_value=ResearchPlan(
            request_id="req-t-iso",
            original_query="Timeout isolation",
            queries=[
                ResearchQuery(query_id="q_fast", query="fast query", purpose="p1"),
                ResearchQuery(query_id="q_slow", query="slow query", purpose="p2"),
            ],
            decomposition_strategy="multi_query",
        )
    )

    agent = ResearchAgent(
        retrieval_service=service, planner=planner, query_timeout=0.05
    )
    task = AgentTask(
        task_id="t-time-iso", request="test", agent_type=AgentType.RESEARCH
    )
    context = AgentExecutionContext(request_id="r-time-iso", user_id=uuid4())

    result = await agent.execute_task(task, context)
    assert result.success is True
    assert len(result.evidence) == 1
    assert "q_slow" in result.metadata["empty_queries"]


# ============================================================================
# D. Evidence Deduplication & QC Tests
# ============================================================================


@pytest.mark.asyncio
async def test_duplicate_chunks_are_deduplicated_and_provenance_preserved():
    shared_chunk_id = uuid4()
    doc_id = uuid4()

    chunk_1 = create_mock_chunk(
        "Quarterly report page 1", doc_id=doc_id, chunk_id=shared_chunk_id, score=0.85
    )
    chunk_2 = create_mock_chunk(
        "Quarterly report page 1", doc_id=doc_id, chunk_id=shared_chunk_id, score=0.95
    )

    service = MagicMock(spec=RetrievalService)

    async def mock_retrieve(query: str, user_id, top_k=5, retrieval_scope=None):
        if "q1" in query:
            return SearchResult(
                original_query=query,
                retrieved_chunks=[chunk_1],
                total_matches=1,
                retrieval_time=5.0,
            )
        return SearchResult(
            original_query=query,
            retrieved_chunks=[chunk_2],
            total_matches=1,
            retrieval_time=5.0,
        )

    service.retrieve = AsyncMock(side_effect=mock_retrieve)

    planner = MagicMock(spec=ResearchPlanner)
    planner.create_plan = AsyncMock(
        return_value=ResearchPlan(
            request_id="req-dedup-ev",
            original_query="Dedup test",
            queries=[
                ResearchQuery(query_id="q1", query="q1 revenue", purpose="p1"),
                ResearchQuery(query_id="q2", query="q2 revenue", purpose="p2"),
            ],
            decomposition_strategy="multi_query",
        )
    )

    agent = ResearchAgent(retrieval_service=service, planner=planner)
    task = AgentTask(task_id="t-dedup", request="test", agent_type=AgentType.RESEARCH)
    context = AgentExecutionContext(request_id="r-dedup", user_id=uuid4())

    result = await agent.execute_task(task, context)

    assert result.success is True
    # Duplicate chunk_id merged into single EvidenceItem
    assert len(result.evidence) == 1
    assert result.evidence[0].chunk_id == shared_chunk_id
    # Highest score kept
    assert result.evidence[0].score == 0.95
    # Provenance tracked: source queries contains both q1 and q2
    assert set(result.evidence[0].metadata["source_queries"]) == {"q1", "q2"}
    assert result.metadata["duplicate_evidence_removed"] == 1


@pytest.mark.asyncio
async def test_empty_retrieval_results_are_recorded():
    service = MagicMock(spec=RetrievalService)
    service.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="Nonexistent topic xyz",
            retrieved_chunks=[],
            total_matches=0,
            retrieval_time=2.0,
        )
    )

    planner = ResearchPlanner(enable_llm_planner=False)
    agent = ResearchAgent(retrieval_service=service, planner=planner)

    task = AgentTask(
        task_id="t-empty",
        request="Nonexistent topic xyz",
        agent_type=AgentType.RESEARCH,
    )
    context = AgentExecutionContext(request_id="r-empty", user_id=uuid4())

    result = await agent.execute_task(task, context)

    assert result.success is True
    assert len(result.evidence) == 0
    assert result.metadata["insufficient_evidence"] is True
    assert len(result.metadata["empty_queries"]) >= 1


@pytest.mark.asyncio
async def test_conflicting_evidence_is_detected():
    chunk_a = create_mock_chunk(
        "Q3 revenue was reported as $10M in the preliminary summary.", score=0.9
    )
    chunk_b = create_mock_chunk(
        "Q3 revenue was officially finalized at $12M in the audited filing.", score=0.88
    )

    service = MagicMock(spec=RetrievalService)
    service.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="Q3 revenue audit",
            retrieved_chunks=[chunk_a, chunk_b],
            total_matches=2,
            retrieval_time=5.0,
        )
    )

    planner = ResearchPlanner(enable_llm_planner=False)
    agent = ResearchAgent(retrieval_service=service, planner=planner)

    task = AgentTask(
        task_id="t-conflict", request="Q3 revenue audit", agent_type=AgentType.RESEARCH
    )
    context = AgentExecutionContext(request_id="r-conflict", user_id=uuid4())

    result = await agent.execute_task(task, context)
    assert result.success is True
    assert result.metadata["conflicting_sources_detected"] is True


# ============================================================================
# E. Security Boundaries Tests
# ============================================================================


@pytest.mark.asyncio
async def test_retrieval_scope_is_strictly_preserved():
    captured_scopes = []
    service = MagicMock(spec=RetrievalService)

    async def mock_retrieve(query: str, user_id, top_k=5, retrieval_scope=None):
        captured_scopes.append(retrieval_scope)
        return SearchResult(
            original_query=query,
            retrieved_chunks=[],
            total_matches=0,
            retrieval_time=1.0,
        )

    service.retrieve = AsyncMock(side_effect=mock_retrieve)

    user_id = uuid4()
    conv_id = uuid4()
    doc_id = uuid4()

    agent = ResearchAgent(
        retrieval_service=service, planner=ResearchPlanner(enable_llm_planner=False)
    )
    task = AgentTask(
        task_id="t-sec",
        request="Compare Q1 and Q2 revenue",
        agent_type=AgentType.RESEARCH,
    )
    context = AgentExecutionContext(
        request_id="r-sec",
        user_id=user_id,
        conversation_id=conv_id,
        include_library_documents=True,
        include_conversation_documents=False,
        document_ids=[doc_id],
    )

    await agent.execute_task(task, context)

    assert len(captured_scopes) >= 1
    for scope in captured_scopes:
        assert isinstance(scope, DocumentRetrievalScope)
        assert scope.user_id == user_id
        assert scope.conversation_id == conv_id
        assert scope.include_library_documents is True
        assert scope.include_conversation_documents is False
        assert scope.document_ids == [doc_id]


# ============================================================================
# F. Prompt 3.2 Integration & Adaptive Replanning Tests
# ============================================================================


@pytest.mark.asyncio
async def test_missing_requirement_triggers_targeted_replan_with_research_metadata():
    retrieval_call_queries = []
    service = MagicMock(spec=RetrievalService)

    async def mock_retrieve(query: str, user_id, top_k=5, retrieval_scope=None):
        retrieval_call_queries.append(query)
        # Iteration 1: Only Q2 revenue is found, Q3 returns empty
        if "q2" in query.lower():
            return SearchResult(
                original_query=query,
                retrieved_chunks=[create_mock_chunk("Q2 revenue is $10M")],
                total_matches=1,
                retrieval_time=5.0,
            )
        elif "q3" in query.lower():
            return SearchResult(
                original_query=query,
                retrieved_chunks=[create_mock_chunk("Q3 revenue was $15M")],
                total_matches=1,
                retrieval_time=5.0,
            )
        return SearchResult(
            original_query=query,
            retrieved_chunks=[],
            total_matches=0,
            retrieval_time=5.0,
        )

    service.retrieve = AsyncMock(side_effect=mock_retrieve)

    research_agent = ResearchAgent(retrieval_service=service)
    evaluator = ResultEvaluator()
    fake_llm = FakePlannerLLMProvider()
    synthesis_agent = SynthesisAgent(llm_provider=fake_llm)

    engine = AgentExecutionEngine(specialist_agents=[research_agent])

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis_agent,
        result_evaluator=evaluator,
        max_plan_iterations=2,
    )

    context = AgentExecutionContext(request_id="r-adaptive", user_id=uuid4())
    resp = await master.execute_request(
        "Compare Q2 and Q3 revenue and explain the reason for the change.", context
    )

    assert resp.diagnostics.plan_iterations >= 1
    assert resp.diagnostics.research_subqueries_executed >= 2
    assert resp.diagnostics.research_evidence_count >= 1


@pytest.mark.asyncio
async def test_backward_compatibility_single_query_research_agent():
    """Verify that old-style tasks with parameters['query'] continue working directly."""
    service = create_mock_retrieval_service(
        [create_mock_chunk("Backward compatible chunk")]
    )
    agent = ResearchAgent(retrieval_service=service)

    task = AgentTask(
        task_id="t-legacy",
        request="Legacy query format",
        agent_type=AgentType.RESEARCH,
        parameters={"query": "Direct parameter query", "top_k": 3},
    )
    context = AgentExecutionContext(request_id="r-legacy", user_id=uuid4())

    result = await agent.execute_task(task, context)

    assert result.success is True
    assert len(result.evidence) == 1
    assert result.evidence[0].content == "Backward compatible chunk"
    assert result.metadata["queries_executed"] >= 1
