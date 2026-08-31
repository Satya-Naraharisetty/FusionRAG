import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.chat.domain.interfaces import (
    HistoryRewriteCache,
    LLMProvider,
    ProviderResponse,
)
from app.chat.domain.models import (
    ChannelRetrievalQueries,
    ContextAction,
    ContextResolution,
    ConversationMessage,
    ConversationTopicState,
    DomainContext,
    MessageRole,
    SourceMode,
)
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentResult,
    AgentTaskStatus,
    AgentType,
    EvidenceItem,
)
from app.chat.services.history_rewriter import (
    LLMHistoryRewriter,
    StateTransitionValidator,
)
from app.chat.services.multi_agent.master_agent import MasterAgent


class InMemoryRewriteCache(HistoryRewriteCache):
    def __init__(self):
        self.store = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self.store[key] = value


class MockJSONLLMProvider(LLMProvider):
    def __init__(self, json_response: dict):
        self.json_response = json_response

    async def generate(self, messages, model, temperature, max_tokens, **kwargs):
        content = json.dumps(self.json_response)
        return ProviderResponse(content=content, usage=None)

    async def stream(self, messages, model, temperature, max_tokens, **kwargs):
        yield


@pytest.mark.asyncio
async def test_state_transition_validator():
    validator = StateTransitionValidator()
    state = ConversationTopicState()

    # Turn 1: START / STANDALONE
    s1 = validator.validate_and_transition(
        current_state=state,
        proposed_action=ContextAction.STANDALONE,
        proposed_subject="Candidate resume",
        proposed_role="Backend and Gen AI Engineer",
        proposed_location=None,
        proposed_entities=["FastAPI", "LangChain"],
        proposed_intent="INTERVIEW_PREPARATION",
        proposed_timeframe=None,
        proposed_compensation_period=None,
    )
    assert s1.active_subject == "Candidate resume"
    assert s1.active_role == "Backend and Gen AI Engineer"
    assert "FastAPI" in s1.active_entities

    # Turn 2: CONTINUE with compensation intent
    s2 = validator.validate_and_transition(
        current_state=s1,
        proposed_action=ContextAction.CONTINUE,
        proposed_subject=None,
        proposed_role=None,
        proposed_location=None,
        proposed_entities=None,
        proposed_intent="COMPENSATION_ESTIMATE",
        proposed_timeframe="monthly",
        proposed_compensation_period="monthly",
    )
    assert s2.active_subject == "Candidate resume"
    assert s2.active_role == "Backend and Gen AI Engineer"
    assert s2.active_intent == "COMPENSATION_ESTIMATE"
    assert s2.compensation_period == "monthly"

    # Turn 3: REFINE adding location
    s3 = validator.validate_and_transition(
        current_state=s2,
        proposed_action=ContextAction.REFINE,
        proposed_subject=None,
        proposed_role=None,
        proposed_location="India",
        proposed_entities=["PyTorch"],
        proposed_intent=None,
        proposed_timeframe=None,
        proposed_compensation_period=None,
    )
    assert s3.active_location == "India"
    assert "PyTorch" in s3.active_entities
    assert "FastAPI" in s3.active_entities

    # Turn 4: SWITCH to unrelated topic
    s4 = validator.validate_and_transition(
        current_state=s3,
        proposed_action=ContextAction.SWITCH,
        proposed_subject="Hyderabad Weather",
        proposed_role=None,
        proposed_location="Hyderabad",
        proposed_entities=["Weather"],
        proposed_intent="WEATHER_QUERY",
        proposed_timeframe="today",
        proposed_compensation_period=None,
    )
    assert s4.active_subject == "Hyderabad Weather"
    assert s4.active_role is None
    assert s4.active_entities == ["Weather"]
    assert "FastAPI" not in s4.active_entities


@pytest.mark.asyncio
async def test_multi_turn_regression_resolution_chain():
    # Mock LLM for the exact user regression scenario: "as per the market give me an estimate value"
    llm_payload = {
        "context_action": "CONTINUE",
        "is_context_dependent": True,
        "intent": "COMPENSATION_ESTIMATE",
        "source_mode": "HYBRID",
        "contextualized_query": "What is the estimated monthly market salary for a Backend and Gen AI Engineer with the candidate's skills and experience?",
        "document_query": "Backend and Gen AI Engineer technical skills experience candidate resume",
        "web_query": "Backend and Gen AI Engineer monthly salary market estimate India 2026",
        "primary_domain": "TECH_CAREER",
        "secondary_domains": ["COMPENSATION", "INDIA"],
        "entities": ["Backend Engineer", "GenAI"],
        "active_subject": "Candidate resume",
        "active_role": "Backend and Gen AI Engineer",
        "active_location": "India",
        "confidence": 0.95,
        "reasoning": "Follow-up asking for market compensation estimate for candidate",
    }
    llm = MockJSONLLMProvider(llm_payload)
    rewriter = LLMHistoryRewriter(llm, "gemini-3.5-flash-lite", InMemoryRewriteCache())

    history = [
        ConversationMessage(
            id=uuid4(),
            conversation_id=uuid4(),
            role=MessageRole.USER,
            content="how much would that person earn per month?",
            created_at=datetime.now(UTC),
        ),
        ConversationMessage(
            id=uuid4(),
            conversation_id=uuid4(),
            role=MessageRole.ASSISTANT,
            content="Based on the provided evidence, there is no information available regarding the person's salary in the resume.",
            created_at=datetime.now(UTC),
        ),
    ]

    res = await rewriter.rewrite(
        question="as per the market give me an estimate value",
        history=history,
    )

    assert res.rewrite_applied is True
    assert res.context_action == ContextAction.CONTINUE
    assert res.source_mode == SourceMode.HYBRID
    assert res.domain_context.primary == "TECH_CAREER"
    assert "Backend and Gen AI Engineer" in res.rewritten_query
    assert "real estate" not in res.retrieval_queries.web_query.lower()
    assert "salary" in res.retrieval_queries.web_query.lower()


@pytest.mark.asyncio
async def test_topic_switch_anti_contamination():
    llm_payload = {
        "context_action": "SWITCH",
        "is_context_dependent": False,
        "intent": "WEATHER_QUERY",
        "source_mode": "WEB_REQUIRED",
        "contextualized_query": "What is the current weather forecast in Hyderabad?",
        "document_query": None,
        "web_query": "Hyderabad current weather today",
        "primary_domain": "WEATHER",
        "secondary_domains": ["HYDERABAD"],
        "entities": ["Hyderabad", "Weather"],
        "active_subject": "Hyderabad Weather",
        "active_location": "Hyderabad",
        "confidence": 0.98,
        "reasoning": "User switched topic from resume to city weather",
    }
    llm = MockJSONLLMProvider(llm_payload)
    rewriter = LLMHistoryRewriter(llm, "gemini-3.5-flash-lite", InMemoryRewriteCache())

    history = [
        ConversationMessage(
            id=uuid4(),
            conversation_id=uuid4(),
            role=MessageRole.USER,
            content="Analyze my resume for backend roles.",
            created_at=datetime.now(UTC),
        ),
        ConversationMessage(
            id=uuid4(),
            conversation_id=uuid4(),
            role=MessageRole.ASSISTANT,
            content="Your resume highlights strong Python and FastAPI experience.",
            created_at=datetime.now(UTC),
        ),
    ]

    res = await rewriter.rewrite(
        question="What's the weather in Hyderabad?",
        history=history,
    )

    # Standalone query cleanly isolates from previous resume context
    assert res.context_action in (ContextAction.STANDALONE, ContextAction.SWITCH)
    assert res.source_mode in (SourceMode.DOCUMENT_ONLY, SourceMode.WEB_REQUIRED)
    assert "resume" not in res.rewritten_query.lower()
    assert "backend" not in res.rewritten_query.lower()

    # Explicit switch query with conversational transition phrase
    res_switch = await rewriter.rewrite(
        question="Actually, forget the resume. What is the salary for a Java developer?",
        history=history,
    )
    assert res_switch.context_action == ContextAction.SWITCH
    assert "resume" not in res_switch.rewritten_query.lower()


def test_evidence_relevance_gate_rejects_real_estate():
    # Setup MasterAgent with mock collaborators
    from unittest.mock import MagicMock

    from app.chat.services.multi_agent.execution_engine import AgentExecutionEngine
    from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent

    master = MasterAgent(
        llm_provider=MagicMock(),
        execution_engine=MagicMock(spec=AgentExecutionEngine),
        synthesis_agent=MagicMock(spec=SynthesisAgent),
    )

    context = AgentExecutionContext(
        request_id="req-123",
        user_id=uuid4(),
        context_resolution=ContextResolution(
            original_query="as per the market give me an estimate value",
            contextualized_query="What is the market salary for a Backend and Gen AI Engineer?",
            is_context_dependent=True,
            context_action=ContextAction.CONTINUE,
            intent="COMPENSATION_ESTIMATE",
            source_mode=SourceMode.HYBRID,
            domain_context=DomainContext(
                primary="TECH_CAREER", secondary=["COMPENSATION"]
            ),
        ),
    )

    # Bad WebSearch result (Real Estate CMA contamination)
    bad_web_result = AgentResult(
        task_id="web_search_1",
        agent_type=AgentType.WEB_SEARCH,
        status=AgentTaskStatus.COMPLETED,
        success=True,
        output="Market valuation methodologies such as Comparative Market Analysis (CMA), comparable sales, and Fannie Mae guidelines...",
        evidence=[
            EvidenceItem(
                document_name="Web: Fannie Mae Comparable Sales",
                content="The sales comparison approach relies on recent sales of comparable properties.",
            )
        ],
    )

    # Good Document Research result
    good_doc_result = AgentResult(
        task_id="research_1",
        agent_type=AgentType.RESEARCH,
        status=AgentTaskStatus.COMPLETED,
        success=True,
        output="Candidate has 3 years experience with FastAPI, PyTorch, and GenAI.",
        evidence=[
            EvidenceItem(
                document_name="Satya_Resume.pdf",
                content="Senior Backend Engineer building LLM RAG pipelines.",
            )
        ],
    )

    filtered_results, rejected_count = master._apply_evidence_relevance_gate(
        results=[good_doc_result, bad_web_result],
        context=context,
    )

    assert rejected_count == 1
    assert filtered_results[0].success is True  # Doc research retained
    assert filtered_results[1].success is False  # Bad web search rejected
    assert "Evidence rejected by Evidence Relevance Gate" in filtered_results[1].error


def test_heuristic_planner_uses_context_resolution():
    from unittest.mock import MagicMock

    from app.chat.services.multi_agent.execution_engine import AgentExecutionEngine
    from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent

    master = MasterAgent(
        llm_provider=MagicMock(),
        execution_engine=MagicMock(spec=AgentExecutionEngine),
        synthesis_agent=MagicMock(spec=SynthesisAgent),
    )

    context = AgentExecutionContext(
        request_id="req-456",
        user_id=uuid4(),
        context_resolution=ContextResolution(
            original_query="as per the market give me an estimate value",
            contextualized_query="What is the market salary for a Backend and Gen AI Engineer?",
            retrieval_queries=ChannelRetrievalQueries(
                document_query="Backend GenAI skills resume",
                web_query="Backend GenAI Engineer salary market estimate India 2026",
            ),
            is_context_dependent=True,
            context_action=ContextAction.CONTINUE,
            intent="COMPENSATION_ESTIMATE",
            source_mode=SourceMode.HYBRID,
            domain_context=DomainContext(primary="TECH_CAREER"),
        ),
    )

    plan = master._plan_heuristic(
        request="What is the market salary for a Backend and Gen AI Engineer?",
        context=context,
    )

    assert len(plan.tasks) == 2
    task_types = [t.agent_type for t in plan.tasks]
    assert AgentType.RESEARCH in task_types
    assert AgentType.WEB_SEARCH in task_types

    web_task = next(t for t in plan.tasks if t.agent_type == AgentType.WEB_SEARCH)
    assert (
        web_task.parameters["query"]
        == "Backend GenAI Engineer salary market estimate India 2026"
    )
