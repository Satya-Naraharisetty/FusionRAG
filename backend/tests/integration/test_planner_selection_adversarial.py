from uuid import uuid4

import pytest

from app.chat.domain.interfaces import LLMProvider, ProviderResponse
from app.chat.domain.models import Usage
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentType,
    ExecutionPlan,
)
from app.chat.services.multi_agent.execution_engine import AgentExecutionEngine
from app.chat.services.multi_agent.master_agent import MasterAgent
from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent


class DummyLLMProvider(LLMProvider):
    """Fallback LLM provider that simulates LLM planner responses or failure fallback."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail

    async def generate(self, messages, model="gemini-3.5-flash-lite", temperature=0.0, max_tokens=1000, **kwargs):
        if self.should_fail:
            raise RuntimeError("Simulated LLM Provider Timeout/Failure")
        return ProviderResponse(
            content="Synthetic plan response",
            usage=Usage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )

    async def stream(self, messages, model="gemini-3.5-flash-lite", temperature=0.0, max_tokens=1000, **kwargs):
        raise NotImplementedError()


@pytest.fixture
def master_agent():
    engine = AgentExecutionEngine(specialist_agents=[])
    synthesis = SynthesisAgent(llm_provider=DummyLLMProvider())
    return MasterAgent(
        llm_provider=DummyLLMProvider(should_fail=True),
        execution_engine=engine,
        synthesis_agent=synthesis,
    )


@pytest.mark.asyncio
async def test_planner_selection_scenario_1_text_factual(master_agent: MasterAgent):
    """
    Scenario 1: Factual Document Query
    Query: 'What does this document say about revenue?'
    Expectation: Selects RESEARCH/DOCUMENT; strictly excludes TABLE, VISION, GRAPH, WEB_SEARCH.
    """
    user_id = uuid4()
    doc_id = uuid4()
    ctx = AgentExecutionContext(
        request_id="scen_1",
        user_id=user_id,
        document_ids=[doc_id],
        include_library_documents=True,
    )

    query = "What does this document say about revenue?"
    plan: ExecutionPlan = await master_agent.create_plan(query, ctx)

    agent_types = [t.agent_type for t in plan.tasks]
    print(f"\n[Scenario 1 Plan Tasks]: {[(t.task_id, t.agent_type.value, t.dependencies) for t in plan.tasks]}")

    assert AgentType.RESEARCH in agent_types or AgentType.DOCUMENT in agent_types
    assert AgentType.TABLE not in agent_types
    assert AgentType.VISION not in agent_types
    assert AgentType.GRAPH not in agent_types
    assert AgentType.WEB_SEARCH not in agent_types


@pytest.mark.asyncio
async def test_planner_selection_scenario_2_cagr_table_math(master_agent: MasterAgent):
    """
    Scenario 2: Structured Tabular Arithmetic / CAGR
    Query: 'Calculate the CAGR from the revenue figures in the table.'
    Expectation: Formulates a DAG where TABLE / RESEARCH feeds into ANALYSIS.
    """
    user_id = uuid4()
    doc_id = uuid4()
    ctx = AgentExecutionContext(
        request_id="scen_2",
        user_id=user_id,
        document_ids=[doc_id],
        include_library_documents=True,
    )

    query = "Calculate the CAGR from the revenue figures in the table."
    plan: ExecutionPlan = await master_agent.create_plan(query, ctx)

    agent_types = [t.agent_type for t in plan.tasks]
    print(f"\n[Scenario 2 Plan Tasks]: {[(t.task_id, t.agent_type.value, t.dependencies) for t in plan.tasks]}")

    assert AgentType.TABLE in agent_types
    assert AgentType.ANALYSIS in agent_types

    # Verify dependency structure: Analysis must depend on Table
    table_task = next(t for t in plan.tasks if t.agent_type == AgentType.TABLE)
    analysis_task = next(t for t in plan.tasks if t.agent_type == AgentType.ANALYSIS)
    assert table_task.task_id in analysis_task.dependencies


@pytest.mark.asyncio
async def test_planner_selection_scenario_3_visual_chart(master_agent: MasterAgent):
    """
    Scenario 3: Visual Inspection
    Query: 'What trend does the chart show in my report?'
    Expectation: Selects VISION; excludes GRAPH, WEB_SEARCH, TABLE.
    """
    user_id = uuid4()
    doc_id = uuid4()
    ctx = AgentExecutionContext(
        request_id="scen_3",
        user_id=user_id,
        document_ids=[doc_id],
        include_library_documents=True,
    )

    query = "What trend does the chart show in my report?"
    plan: ExecutionPlan = await master_agent.create_plan(query, ctx)

    agent_types = [t.agent_type for t in plan.tasks]
    print(f"\n[Scenario 3 Plan Tasks]: {[(t.task_id, t.agent_type.value, t.dependencies) for t in plan.tasks]}")

    assert AgentType.VISION in agent_types
    assert AgentType.GRAPH not in agent_types
    assert AgentType.WEB_SEARCH not in agent_types


@pytest.mark.asyncio
async def test_planner_selection_scenario_4_graph_relationship(master_agent: MasterAgent):
    """
    Scenario 4: Knowledge Graph Relationship
    Query: 'How is Company A related to Company B in my uploaded documents?'
    Expectation: Selects GRAPH; excludes VISION, WEB_SEARCH, TABLE.
    """
    user_id = uuid4()
    doc_id = uuid4()
    ctx = AgentExecutionContext(
        request_id="scen_4",
        user_id=user_id,
        document_ids=[doc_id],
        include_library_documents=True,
    )

    query = "How is Company A related to Company B in my uploaded documents?"
    plan: ExecutionPlan = await master_agent.create_plan(query, ctx)

    agent_types = [t.agent_type for t in plan.tasks]
    print(f"\n[Scenario 4 Plan Tasks]: {[(t.task_id, t.agent_type.value, t.dependencies) for t in plan.tasks]}")

    assert AgentType.GRAPH in agent_types
    assert AgentType.VISION not in agent_types
    assert AgentType.WEB_SEARCH not in agent_types


@pytest.mark.asyncio
async def test_planner_selection_scenario_5_hybrid_doc_web_math(master_agent: MasterAgent):
    """
    Scenario 5: Hybrid Document + Live Web + Calculation
    Query: 'Compare the revenue in my document with online market data and calculate the difference.'
    Expectation: Formulates a DAG with RESEARCH + WEB_SEARCH concurrently feeding into ANALYSIS.
    """
    user_id = uuid4()
    doc_id = uuid4()
    ctx = AgentExecutionContext(
        request_id="scen_5",
        user_id=user_id,
        document_ids=[doc_id],
        include_library_documents=True,
    )

    query = "Compare the revenue in my document with online market data and calculate the difference."
    plan: ExecutionPlan = await master_agent.create_plan(query, ctx)

    agent_types = [t.agent_type for t in plan.tasks]
    print(f"\n[Scenario 5 Plan Tasks]: {[(t.task_id, t.agent_type.value, t.dependencies) for t in plan.tasks]}")

    assert AgentType.RESEARCH in agent_types or AgentType.TABLE in agent_types
    assert AgentType.WEB_SEARCH in agent_types
    assert AgentType.ANALYSIS in agent_types

    # Verify Analysis depends on upstream tasks
    analysis_task = next(t for t in plan.tasks if t.agent_type == AgentType.ANALYSIS)
    assert len(analysis_task.dependencies) >= 1


@pytest.mark.asyncio
async def test_planner_selection_scenario_6_complex_multi_specialist(master_agent: MasterAgent):
    """
    Scenario 6: Complex Multi-Specialist Request
    Query: 'Extract the table from my document, calculate the totals, and explain the relationships between entities.'
    Expectation: Selects multiple specialists in a coordinated DAG.
    """
    user_id = uuid4()
    doc_id = uuid4()
    ctx = AgentExecutionContext(
        request_id="scen_6",
        user_id=user_id,
        document_ids=[doc_id],
        include_library_documents=True,
    )

    query = "Extract the table from my document, calculate the totals, and explain the relationships between entities."
    plan: ExecutionPlan = await master_agent.create_plan(query, ctx)

    agent_types = [t.agent_type for t in plan.tasks]
    print(f"\n[Scenario 6 Plan Tasks]: {[(t.task_id, t.agent_type.value, t.dependencies) for t in plan.tasks]}")

    assert AgentType.TABLE in agent_types
    assert AgentType.ANALYSIS in agent_types
    assert len(plan.tasks) >= 2


@pytest.mark.asyncio
async def test_llm_planner_json_schema_parsing():
    """
    Tests that when an LLM provider returns a valid multi-agent DAG JSON,
    MasterAgent parses, validates, and constructs the exact multi-agent ExecutionPlan.
    """
    class MockLLMPlanProvider(LLMProvider):
        async def generate(self, messages, model="gemini-3.5-flash-lite", temperature=0.0, max_tokens=1000, **kwargs):
            plan_json = """{
                "reasoning_summary": "Comprehensive multi-specialist investigation plan",
                "tasks": [
                    {
                        "task_id": "task_1_research",
                        "agent_type": "RESEARCH",
                        "request": "Retrieve relevant sections from document",
                        "dependencies": [],
                        "parameters": {"query": "company financials and org chart"}
                    },
                    {
                        "task_id": "task_2_table",
                        "agent_type": "TABLE",
                        "request": "Extract financial revenue table",
                        "dependencies": ["task_1_research"],
                        "parameters": {}
                    },
                    {
                        "task_id": "task_3_graph",
                        "agent_type": "GRAPH",
                        "request": "Traverse entity relationships",
                        "dependencies": ["task_1_research"],
                        "parameters": {"query": "corporate ownership"}
                    },
                    {
                        "task_id": "task_4_analysis",
                        "agent_type": "ANALYSIS",
                        "request": "Compute CAGR from table",
                        "dependencies": ["task_2_table"],
                        "parameters": {"action": "calculate"}
                    }
                ]
            }"""
            return ProviderResponse(
                content=plan_json,
                usage=Usage(prompt_tokens=50, completion_tokens=80, total_tokens=130),
            )

        async def stream(self, messages, model="gemini-3.5-flash-lite", temperature=0.0, max_tokens=1000, **kwargs):
            raise NotImplementedError()

    engine = AgentExecutionEngine(specialist_agents=[])
    synthesis = SynthesisAgent(llm_provider=MockLLMPlanProvider())
    master = MasterAgent(
        llm_provider=MockLLMPlanProvider(),
        execution_engine=engine,
        synthesis_agent=synthesis,
    )

    ctx = AgentExecutionContext(request_id="llm_plan_test", user_id=uuid4())
    plan = await master.create_plan("Analyze company financials, ownership, and revenue table", ctx)

    print(f"\n[LLM Generated Plan Tasks ({len(plan.tasks)})]:")
    for t in plan.tasks:
        print(f"  {t.task_id} ({t.agent_type.value}) -> depends_on={t.dependencies}")

    assert len(plan.tasks) == 4
    task_types = [t.agent_type for t in plan.tasks]
    assert task_types == [AgentType.RESEARCH, AgentType.TABLE, AgentType.GRAPH, AgentType.ANALYSIS]

    # Verify topological wave structure
    task_map = {t.task_id: t for t in plan.tasks}
    assert task_map["task_1_research"].dependencies == []
    assert "task_1_research" in task_map["task_2_table"].dependencies
    assert "task_1_research" in task_map["task_3_graph"].dependencies
    assert "task_2_table" in task_map["task_4_analysis"].dependencies
