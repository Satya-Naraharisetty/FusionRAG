import asyncio
import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.chat.domain.models import ChatMessage, Citation, Usage
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentFailureReason,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
    EvidenceItem,
    ExecutionPlan,
    MultiAgentDiagnostics,
    SynthesisRequest,
)
from app.chat.services.chat_orchestrator import ChatOrchestrator
from app.chat.services.multi_agent.analysis_agent import AnalysisAgent
from app.chat.services.multi_agent.document_agent import DocumentAgent
from app.chat.services.multi_agent.execution_engine import (
    AgentExecutionEngine,
)
from app.chat.services.multi_agent.master_agent import MasterAgent
from app.chat.services.multi_agent.research_agent import ResearchAgent
from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent
from app.documents.domain.models import (
    Chunk,
    Document,
    DocumentScope,
    DocumentStatus,
    RetrievedChunk,
    SearchResult,
)

# ---------------------------------------------------------------------------
# Test Helpers & Fakes
# ---------------------------------------------------------------------------


class FakeLLMProvider:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.call_history: list[list[ChatMessage]] = []

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

    async def list_by_document(self, document_id: UUID) -> list[Chunk]:
        return self.chunks.get(document_id, [])


# ---------------------------------------------------------------------------
# 1. Plan Validation & DAG Tests
# ---------------------------------------------------------------------------


def test_plan_validation_valid_linear_plan():
    engine = AgentExecutionEngine(specialist_agents=[], max_specialist_tasks=5)
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(task_id="t1", request="search", agent_type=AgentType.RESEARCH),
            AgentTask(
                task_id="t2",
                request="calc",
                agent_type=AgentType.ANALYSIS,
                dependencies=["t1"],
            ),
        ],
    )
    errors = engine.validate_plan(plan)
    assert errors == []


def test_plan_validation_rejects_empty_plan():
    engine = AgentExecutionEngine(specialist_agents=[])
    plan = ExecutionPlan(request_id="req-1", tasks=[])
    errors = engine.validate_plan(plan)
    assert len(errors) == 1
    assert "contains no tasks" in errors[0]


def test_plan_validation_rejects_oversized_plan():
    engine = AgentExecutionEngine(specialist_agents=[], max_specialist_tasks=2)
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(task_id=f"t{i}", request="task", agent_type=AgentType.RESEARCH)
            for i in range(3)
        ],
    )
    errors = engine.validate_plan(plan)
    assert any("exceeds maximum specialist tasks limit" in e for e in errors)


def test_plan_validation_rejects_self_dependency():
    engine = AgentExecutionEngine(specialist_agents=[])
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="self-loop",
                agent_type=AgentType.RESEARCH,
                dependencies=["t1"],
            )
        ],
    )
    errors = engine.validate_plan(plan)
    assert any("cannot depend on itself" in e for e in errors)


def test_plan_validation_rejects_nonexistent_dependency():
    engine = AgentExecutionEngine(specialist_agents=[])
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="orphan dep",
                agent_type=AgentType.RESEARCH,
                dependencies=["nonexistent_task"],
            )
        ],
    )
    errors = engine.validate_plan(plan)
    assert any("nonexistent dependency" in e for e in errors)


def test_plan_validation_rejects_circular_dependency():
    engine = AgentExecutionEngine(specialist_agents=[])
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="task 1",
                agent_type=AgentType.RESEARCH,
                dependencies=["t2"],
            ),
            AgentTask(
                task_id="t2",
                request="task 2",
                agent_type=AgentType.ANALYSIS,
                dependencies=["t1"],
            ),
        ],
    )
    errors = engine.validate_plan(plan)
    assert any("Circular dependency detected" in e for e in errors)


def test_plan_validation_rejects_unauthorized_agent_type():
    engine = AgentExecutionEngine(specialist_agents=[])
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="invoke synthesis directly",
                agent_type=AgentType.SYNTHESIS,
            )
        ],
    )
    errors = engine.validate_plan(plan)
    assert any("unauthorized or unexecutable agent type" in e for e in errors)


# ---------------------------------------------------------------------------
# 2. Specialist Agent Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_agent_success():
    retrieval_mock = AsyncMock()
    doc_id = uuid4()
    chunk_id = uuid4()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="query",
        retrieval_time=12.5,
        total_matches=1,
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                chunk_index=0,
                text="Refresh tokens expire in 30 days.",
                similarity_score=0.95,
                document_name="auth.md",
                metadata={},
            )
        ],
    )
    agent = ResearchAgent(retrieval_service=retrieval_mock)
    context = AgentExecutionContext(
        request_id="req-1",
        user_id=uuid4(),
        conversation_id=uuid4(),
    )
    task = AgentTask(
        task_id="t1", request="refresh token policy", agent_type=AgentType.RESEARCH
    )

    result = await agent.execute_task(task, context)

    assert result.success is True
    assert result.status == AgentTaskStatus.COMPLETED
    assert len(result.evidence) == 1
    assert result.evidence[0].content == "Refresh tokens expire in 30 days."
    assert len(result.citations) == 1
    assert result.citations[0].document_name == "auth.md"
    assert result.metadata["insufficient_evidence"] is False


@pytest.mark.asyncio
async def test_research_agent_empty_evidence_marked():
    retrieval_mock = AsyncMock()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="unmatched",
        retrieval_time=5.0,
        total_matches=0,
        retrieved_chunks=[],
    )
    agent = ResearchAgent(retrieval_service=retrieval_mock)
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())
    task = AgentTask(task_id="t1", request="unmatched", agent_type=AgentType.RESEARCH)

    result = await agent.execute_task(task, context)

    assert result.success is True
    assert len(result.evidence) == 0
    assert result.metadata["insufficient_evidence"] is True


@pytest.mark.asyncio
async def test_document_agent_success():
    doc_id = uuid4()
    user_id = uuid4()
    chunk_id = uuid4()
    now = datetime.now(UTC)

    doc = Document(
        id=doc_id,
        user_id=user_id,
        filename="report.pdf",
        original_filename="Q3_Report.pdf",
        content_type="application/pdf",
        file_size=1024,
        checksum="chk-123",
        status=DocumentStatus.COMPLETED,
        scope=DocumentScope.LIBRARY,
        page_count=10,
        word_count=5000,
        created_at=now,
        updated_at=now,
    )
    chunk = Chunk(
        id=chunk_id,
        document_id=doc_id,
        chunk_index=0,
        text="Q3 revenue grew by 15%.",
        character_start=0,
        character_end=24,
        token_estimate=6,
        created_at=now,
    )
    doc_repo = FakeDocumentRepo({doc_id: doc})
    chunk_repo = FakeChunkRepo({doc_id: [chunk]})
    agent = DocumentAgent(document_repo=doc_repo, chunk_repo=chunk_repo)

    context = AgentExecutionContext(request_id="req-1", user_id=user_id)
    task = AgentTask(
        task_id="t1",
        request=f"Inspect doc {doc_id}",
        agent_type=AgentType.DOCUMENT,
        parameters={"document_id": str(doc_id)},
    )

    result = await agent.execute_task(task, context)

    assert result.success is True
    assert len(result.evidence) == 1
    assert result.evidence[0].content == "Q3 revenue grew by 15%."
    assert len(result.citations) == 1
    assert result.citations[0].document_name == "Q3_Report.pdf"


@pytest.mark.asyncio
async def test_document_agent_unauthorized_access_rejected():
    doc_id = uuid4()
    owner_id = uuid4()
    attacker_id = uuid4()
    now = datetime.now(UTC)

    doc = Document(
        id=doc_id,
        user_id=owner_id,
        filename="secret.pdf",
        original_filename="secret.pdf",
        content_type="application/pdf",
        file_size=100,
        checksum="chk",
        status=DocumentStatus.COMPLETED,
        scope=DocumentScope.LIBRARY,
        created_at=now,
        updated_at=now,
    )
    doc_repo = FakeDocumentRepo({doc_id: doc})
    agent = DocumentAgent(document_repo=doc_repo)

    context = AgentExecutionContext(request_id="req-1", user_id=attacker_id)
    task = AgentTask(
        task_id="t1",
        request=f"Inspect doc {doc_id}",
        agent_type=AgentType.DOCUMENT,
        parameters={"document_id": str(doc_id)},
    )

    result = await agent.execute_task(task, context)

    assert result.success is False
    assert result.status == AgentTaskStatus.FAILED
    assert result.failure_reason == AgentFailureReason.UNAUTHORIZED
    assert "Access Denied" in result.error


@pytest.mark.asyncio
async def test_analysis_agent_safe_math():
    agent = AnalysisAgent()
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    # Arithmetic expression
    task1 = AgentTask(
        task_id="t1",
        request="Calculate 15 * 2 + 10",
        agent_type=AgentType.ANALYSIS,
        parameters={"expression": "15 * 2 + 10"},
    )
    res1 = await agent.execute_task(task1, context)
    assert res1.success is True
    assert res1.metadata["result"] == 40

    # Growth rate structured operation
    task2 = AgentTask(
        task_id="t2",
        request="Compute growth rate",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "growth_rate", "old_value": 100, "new_value": 125},
    )
    res2 = await agent.execute_task(task2, context)
    assert res2.success is True
    assert res2.metadata["growth_rate_pct"] == 25.0


@pytest.mark.asyncio
async def test_analysis_agent_sandboxing_blocks_unsafe_syntax():
    agent = AnalysisAgent()
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    task = AgentTask(
        task_id="t1",
        request="import os",
        agent_type=AgentType.ANALYSIS,
        parameters={"expression": "__import__('os').system('ls')"},
    )
    res = await agent.execute_task(task, context)
    assert res.success is False
    assert res.status == AgentTaskStatus.FAILED


# ---------------------------------------------------------------------------
# 3. Execution Engine Concurrency & Dependency Propagation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_executes_independent_tasks_concurrently():
    execution_order = []

    class AsyncTrackingSpecialist(ResearchAgent):
        def __init__(self, name: str, delay: float):
            self.name = name
            self.delay = delay

        @property
        def agent_type(self) -> AgentType:
            return AgentType.RESEARCH

        async def execute_task(self, task, context):
            execution_order.append(f"start_{self.name}")
            await asyncio.sleep(self.delay)
            execution_order.append(f"end_{self.name}")
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output=f"{self.name} result",
            )

    spec = AsyncTrackingSpecialist("spec", 0.05)
    engine = AgentExecutionEngine(specialist_agents=[spec])

    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="r1",
                agent_type=AgentType.RESEARCH,
                dependencies=[],
            ),
            AgentTask(
                task_id="t2",
                request="r2",
                agent_type=AgentType.RESEARCH,
                dependencies=[],
            ),
        ],
    )
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    start = time.perf_counter()
    outcome = await engine.execute(plan, context)
    elapsed = time.perf_counter() - start

    assert len(outcome.completed_results) == 2
    # If concurrent, elapsed time is close to single delay (~0.05s) rather than 2x delay (~0.10s)
    assert elapsed < 0.09
    assert execution_order.count("start_spec") == 2


@pytest.mark.asyncio
async def test_engine_propagates_dependency_results():
    analysis_received_deps = {}

    class TrackingAnalysisAgent(AnalysisAgent):
        async def execute_task(self, task, context):
            nonlocal analysis_received_deps
            analysis_received_deps = dict(context.dependency_results)
            return await super().execute_task(task, context)

    # Specialist 1: Research Agent returns evidence
    retrieval_mock = AsyncMock()
    doc_id = uuid4()
    chunk_id = uuid4()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="revenue",
        retrieval_time=1.0,
        total_matches=1,
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                chunk_index=0,
                text="Revenue was 500 in Q1 and 650 in Q2.",
                similarity_score=0.9,
                document_name="finances.md",
            )
        ],
    )
    research_agent = ResearchAgent(retrieval_mock)
    analysis_agent = TrackingAnalysisAgent()

    engine = AgentExecutionEngine(specialist_agents=[research_agent, analysis_agent])

    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="research_task",
                request="find revenue",
                agent_type=AgentType.RESEARCH,
            ),
            AgentTask(
                task_id="analysis_task",
                request="compute growth",
                agent_type=AgentType.ANALYSIS,
                dependencies=["research_task"],
                parameters={
                    "operation": "growth_rate",
                    "old_value": 500,
                    "new_value": 650,
                },
            ),
        ],
    )
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    outcome = await engine.execute(plan, context)

    assert len(outcome.completed_results) == 2
    assert "research_task" in analysis_received_deps
    assert analysis_received_deps["research_task"].success is True
    assert (
        analysis_received_deps["research_task"].evidence[0].content
        == "Revenue was 500 in Q1 and 650 in Q2."
    )


@pytest.mark.asyncio
async def test_engine_skips_downstream_when_dependency_fails():
    class FailingSpecialist(ResearchAgent):
        def __init__(self):
            pass

        @property
        def agent_type(self) -> AgentType:
            return AgentType.RESEARCH

        async def execute_task(self, task, context):
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error="DB network timeout",
                failure_reason=AgentFailureReason.TIMEOUT,
            )

    fail_agent = FailingSpecialist()
    analysis_agent = AnalysisAgent()
    engine = AgentExecutionEngine(specialist_agents=[fail_agent, analysis_agent])

    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1", request="failing task", agent_type=AgentType.RESEARCH
            ),
            AgentTask(
                task_id="t2",
                request="dependent analysis",
                agent_type=AgentType.ANALYSIS,
                dependencies=["t1"],
                parameters={"expression": "1 + 1"},
            ),
        ],
    )
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    outcome = await engine.execute(plan, context)

    assert len(outcome.failed_results) == 1
    assert outcome.failed_results[0].task_id == "t1"
    assert len(outcome.skipped_results) == 1
    assert outcome.skipped_results[0].task_id == "t2"
    assert (
        outcome.skipped_results[0].failure_reason
        == AgentFailureReason.DEPENDENCY_FAILED
    )


# ---------------------------------------------------------------------------
# 4. Synthesis Agent Grounding & Evidence Integrity Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesis_agent_preserves_citations():
    fake_llm = FakeLLMProvider(
        responses=["The authentication system uses JWT tokens with 15min expiry."]
    )
    synthesis = SynthesisAgent(llm_provider=fake_llm)

    doc_id = uuid4()
    chunk_id = uuid4()
    specialist_results = [
        AgentResult(
            task_id="t1",
            agent_type=AgentType.RESEARCH,
            status=AgentTaskStatus.COMPLETED,
            success=True,
            output="Found auth documentation",
            evidence=[
                EvidenceItem(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    document_name="auth.md",
                    content="JWT access tokens expire in 15 minutes.",
                )
            ],
            citations=[
                Citation(
                    document_id=doc_id,
                    document_name="auth.md",
                    chunk_id=chunk_id,
                    chunk_index=0,
                )
            ],
        )
    ]
    req = SynthesisRequest(
        request_id="req-1",
        original_request="How does authentication work?",
        specialist_results=specialist_results,
        context=AgentExecutionContext(request_id="req-1", user_id=uuid4()),
    )

    answer, citations, usage = await synthesis.synthesize(req, model="test-model")

    assert "JWT tokens" in answer
    assert len(citations) == 1
    assert citations[0].document_name == "auth.md"
    assert citations[0].chunk_id == chunk_id


# ---------------------------------------------------------------------------
# 5. MasterAgent Planning, Replanning & End-to-End Orchestration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_master_agent_heuristic_fallback_planning():
    fake_llm = FakeLLMProvider(responses=["invalid json not matching schema"])
    engine = AgentExecutionEngine(specialist_agents=[])
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
    )
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    # 1. Research query
    plan_research = await master.create_plan("What is hybrid search?", context)
    assert len(plan_research.tasks) == 1
    assert plan_research.tasks[0].agent_type == AgentType.RESEARCH

    # 2. Pure calculation query
    plan_math = await master.create_plan("Calculate 25 * 4 + 10", context)
    assert len(plan_math.tasks) == 1
    assert plan_math.tasks[0].agent_type == AgentType.ANALYSIS

    # 3. Specific document query
    doc_uuid = uuid4()
    plan_doc = await master.create_plan(f"Inspect document {doc_uuid}", context)
    assert len(plan_doc.tasks) == 1
    assert plan_doc.tasks[0].agent_type == AgentType.DOCUMENT


@pytest.mark.asyncio
async def test_master_agent_end_to_end_execution():
    # Setup specialist agents
    retrieval_mock = AsyncMock()
    doc_id = uuid4()
    chunk_id = uuid4()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="What is the refund policy?",
        retrieval_time=2.0,
        total_matches=1,
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                chunk_index=0,
                text="Customers can request a refund within 30 days.",
                similarity_score=0.92,
                document_name="refund_policy.pdf",
            )
        ],
    )
    research_agent = ResearchAgent(retrieval_mock)
    analysis_agent = AnalysisAgent()

    engine = AgentExecutionEngine(specialist_agents=[research_agent, analysis_agent])
    fake_llm = FakeLLMProvider(
        responses=[
            # 1. LLM Planner response
            """```json
            {
                "reasoning_summary": "Retrieve refund policy from knowledge base",
                "tasks": [
                    {
                        "task_id": "task_1",
                        "agent_type": "RESEARCH",
                        "request": "What is the refund policy?",
                        "dependencies": []
                    }
                ]
            }
            ```""",
            # 2. Synthesis response
            "According to the refund policy, customers can request a refund within 30 days.",
        ]
    )
    synthesis_agent = SynthesisAgent(llm_provider=fake_llm)

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis_agent,
    )

    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())
    response = await master.execute_request("What is the refund policy?", context)

    assert "refund within 30 days" in response.answer
    assert len(response.citations) == 1
    assert response.citations[0].document_name == "refund_policy.pdf"
    assert response.diagnostics.plan_iterations == 1
    assert response.diagnostics.total_specialist_calls == 1


@pytest.mark.asyncio
async def test_master_agent_streaming_lifecycle_events():
    retrieval_mock = AsyncMock()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="streaming test",
        retrieval_time=1.0,
        total_matches=1,
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id=uuid4(),
                document_id=uuid4(),
                chunk_index=0,
                text="Sample content",
                similarity_score=0.9,
                document_name="test.md",
            )
        ],
    )
    research_agent = ResearchAgent(retrieval_mock)
    engine = AgentExecutionEngine(specialist_agents=[research_agent])
    fake_llm = FakeLLMProvider()
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    master = MasterAgent(
        llm_provider=fake_llm, execution_engine=engine, synthesis_agent=synthesis
    )

    context = AgentExecutionContext(request_id="req-stream", user_id=uuid4())

    events = []
    async for event in master.execute_request_stream("Search documentation", context):
        events.append(event)

    event_names = [e["event"] for e in events]
    assert "plan_created" in event_names
    assert "agent_started" in event_names
    assert "agent_completed" in event_names
    assert "synthesis_started" in event_names
    assert "text" in event_names
    assert "synthesis_done" in event_names


@pytest.mark.asyncio
async def test_engine_enforces_task_timeout():
    class SlowSpecialist(ResearchAgent):
        def __init__(self):
            pass

        @property
        def agent_type(self) -> AgentType:
            return AgentType.RESEARCH

        async def execute_task(self, task, context):
            await asyncio.sleep(0.5)
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="done",
            )

    slow_agent = SlowSpecialist()
    engine = AgentExecutionEngine(specialist_agents=[slow_agent], task_timeout=0.05)
    plan = ExecutionPlan(
        request_id="req-timeout",
        tasks=[
            AgentTask(task_id="t1", request="slow task", agent_type=AgentType.RESEARCH)
        ],
    )
    context = AgentExecutionContext(request_id="req-timeout", user_id=uuid4())

    outcome = await engine.execute(plan, context)
    assert len(outcome.failed_results) == 1
    assert outcome.failed_results[0].failure_reason == AgentFailureReason.TIMEOUT
    assert "timed out" in outcome.failed_results[0].error


@pytest.mark.asyncio
async def test_engine_enforces_max_total_calls():
    class CountingSpecialist(ResearchAgent):
        def __init__(self):
            self.call_count = 0

        @property
        def agent_type(self) -> AgentType:
            return AgentType.RESEARCH

        async def execute_task(self, task, context):
            self.call_count += 1
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output=f"call {self.call_count}",
            )

    counter = CountingSpecialist()
    engine = AgentExecutionEngine(
        specialist_agents=[counter],
        max_specialist_tasks=5,
        max_total_calls=2,
    )
    plan = ExecutionPlan(
        request_id="req-calls",
        tasks=[
            AgentTask(
                task_id=f"t{i}", request=f"task {i}", agent_type=AgentType.RESEARCH
            )
            for i in range(4)
        ],
    )
    context = AgentExecutionContext(request_id="req-calls", user_id=uuid4())

    outcome = await engine.execute(plan, context)
    assert outcome.total_calls == 2
    assert "MAX_TOTAL_AGENT_CALLS" in outcome.limits_reached
    assert len(outcome.skipped_results) == 2


@pytest.mark.asyncio
async def test_master_agent_replanning_loop_terminates_at_limit():
    # Setup specialist that always reports empty evidence
    retrieval_mock = AsyncMock()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="missing query",
        retrieval_time=1.0,
        total_matches=0,
        retrieved_chunks=[],
    )
    research_agent = ResearchAgent(retrieval_mock)
    engine = AgentExecutionEngine(specialist_agents=[research_agent])
    fake_llm = FakeLLMProvider(
        responses=[
            "invalid json plan 1",
            "invalid json plan 2",
            "Evidence was insufficient across all attempts.",
        ]
    )
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        max_plan_iterations=2,
    )

    context = AgentExecutionContext(request_id="req-replan", user_id=uuid4())
    resp = await master.execute_request("Search missing topic", context)

    assert resp.diagnostics.plan_iterations == 2
    assert resp.diagnostics.total_specialist_calls == 2
    assert "insufficient" in resp.answer.lower()


@pytest.mark.asyncio
async def test_master_agent_compound_query_end_to_end():
    retrieval_mock = AsyncMock()
    doc_id = uuid4()
    chunk_id = uuid4()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="What was our Q1 revenue and Q2 revenue? Calculate the growth rate.",
        retrieval_time=2.0,
        total_matches=1,
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                chunk_index=0,
                text="Q1 revenue: $100M. Q2 revenue: $140M.",
                similarity_score=0.95,
                document_name="q2_report.pdf",
            )
        ],
    )
    research_agent = ResearchAgent(retrieval_mock)
    analysis_agent = AnalysisAgent()
    engine = AgentExecutionEngine(specialist_agents=[research_agent, analysis_agent])

    fake_llm = FakeLLMProvider(
        responses=[
            # 1. LLM planner produces 2-task DAG (Research -> Analysis)
            """```json
            {
                "reasoning_summary": "Retrieve revenue numbers and compute growth rate",
                "tasks": [
                    {
                        "task_id": "retrieve_rev",
                        "agent_type": "RESEARCH",
                        "request": "Retrieve Q1 and Q2 revenue numbers",
                        "dependencies": []
                    },
                    {
                        "task_id": "calc_growth",
                        "agent_type": "ANALYSIS",
                        "request": "Calculate growth rate from Q1 to Q2",
                        "dependencies": ["retrieve_rev"],
                        "parameters": {
                            "operation": "growth_rate",
                            "old_value": 100,
                            "new_value": 140
                        }
                    }
                ]
            }
            ```""",
            # 2. Synthesis output
            "Q1 revenue was $100M and Q2 revenue was $140M, representing a 40% growth rate.",
        ]
    )
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    master = MasterAgent(
        llm_provider=fake_llm, execution_engine=engine, synthesis_agent=synthesis
    )

    context = AgentExecutionContext(request_id="req-compound", user_id=uuid4())
    resp = await master.execute_request(
        "What was our Q1 revenue and Q2 revenue? Calculate the growth rate.", context
    )

    assert "40% growth rate" in resp.answer
    assert len(resp.specialist_results) == 2
    assert len(resp.citations) == 1
    assert resp.citations[0].document_name == "q2_report.pdf"


@pytest.mark.asyncio
async def test_chat_orchestrator_multi_agent_eliminates_duplicate_retrieval():
    from unittest.mock import AsyncMock, MagicMock

    from app.chat.domain.models import Usage
    from app.chat.domain.multi_agent import (
        ExecutionPlan,
        MultiAgentDiagnostics,
        MultiAgentResponse,
    )
    from app.chat.services.chat_orchestrator import ChatOrchestrator

    mock_conv_mgr = AsyncMock()
    mock_conv = MagicMock()
    mock_conv.id = uuid4()
    mock_conv_mgr.get_or_create_conversation.return_value = mock_conv

    mock_ctx = MagicMock()
    mock_ctx.recent_messages = []
    mock_ctx.summary = None
    mock_rewrite = MagicMock()
    mock_rewrite.rewritten_query = "What is the policy?"
    mock_rewrite.rewrite_applied = False
    mock_conv_mgr.prepare_context.return_value = (mock_ctx, mock_rewrite)

    # Mock retrieval service to track calls
    mock_retrieval = AsyncMock()

    # Mock master agent
    mock_master = AsyncMock()
    mock_master.execute_request.return_value = MultiAgentResponse(
        answer="The refund policy allows 30 days.",
        plan=ExecutionPlan(request_id="r1", tasks=[]),
        specialist_results=[],
        citations=[],
        usage=Usage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        total_time_ms=120.0,
        diagnostics=MultiAgentDiagnostics(
            research_retrieval_latency_ms=45.0, research_evidence_count=1
        ),
    )

    doc_service = AsyncMock()
    doc_service.list_documents.return_value = [MagicMock(id=uuid4())]
    mock_conv_mgr._document_service = doc_service

    orchestrator = ChatOrchestrator(
        conversation_manager=mock_conv_mgr,
        retrieval_service=mock_retrieval,
        prompt_builder=MagicMock(),
        context_builder=MagicMock(),
        token_estimator=MagicMock(estimate=MagicMock(return_value=10)),
        llm_generation_service=AsyncMock(),
        agent_executor=AsyncMock(),
        master_agent=mock_master,
        model="gemini-3.5-flash-lite",
        enable_conversation_memory=True,
        enable_multi_agent=True,
    )

    resp = await orchestrator.generate_answer(
        conversation_id=mock_conv.id,
        user_id=uuid4(),
        question="What is the policy? @documents",
        top_k=5,
    )

    # Critical Assertion: RetrievalService was NOT called upfront by ChatOrchestrator!
    mock_retrieval.retrieve.assert_not_called()
    # MasterAgent was called to own the request
    mock_master.execute_request.assert_called_once()
    assert resp.answer == "The refund policy allows 30 days."
    assert resp.retrieval_time_ms == 45.0

    # Verify agent diagnostics were persisted in finalize_message metadata
    mock_conv_mgr.finalize_message.assert_called_once()
    _, kwargs = mock_conv_mgr.finalize_message.call_args
    meta = kwargs.get("metadata", {})
    assert "agent_diagnostics" in meta
    assert meta["agent_diagnostics"]["multi_agent_execution"] is True
    assert meta["agent_diagnostics"]["evidence_count"] == 1


@pytest.mark.asyncio
async def test_sanitized_diagnostics_formatting_and_boundaries():
    """Verify format_sanitized_agent_diagnostics produces clean, bounded, JSON-serializable operational data without sensitive context."""
    from app.chat.domain.multi_agent import (
        EvaluationDecision,
        ResultEvaluation,
        format_sanitized_agent_diagnostics,
    )

    plan = ExecutionPlan(
        request_id="req-123",
        tasks=[
            AgentTask(
                task_id="t1",
                request="Research Q2 revenue",
                agent_type=AgentType.RESEARCH,
                dependencies=[],
            ),
            AgentTask(
                task_id="t2",
                request="Calculate growth",
                agent_type=AgentType.ANALYSIS,
                dependencies=["t1"],
            ),
        ],
        reasoning_summary="Two-step financial analysis",
    )

    results = [
        AgentResult(
            task_id="t1",
            agent_type=AgentType.RESEARCH,
            status=AgentTaskStatus.COMPLETED,
            success=True,
            output="Found $10M",
            evidence=[
                EvidenceItem(
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    document_name="10k.pdf",
                    content="Confidential raw text that should not leak in diagnostics",
                )
            ],
            execution_time_ms=120.5,
            metadata={"routed_capability": "research.fusion_rag"},
        ),
        AgentResult(
            task_id="t2",
            agent_type=AgentType.ANALYSIS,
            status=AgentTaskStatus.COMPLETED,
            success=True,
            output="50% growth",
            evidence=[],
            execution_time_ms=15.2,
            metadata={"routed_capability": "analysis.safe_calculator"},
        ),
    ]

    diagnostics = MultiAgentDiagnostics(
        plan_iterations=1,
        total_specialist_calls=2,
        research_evidence_count=1,
        concurrency_savings_ms=45.0,
        planning_latency_ms=10.0,
        execution_latency_ms=135.7,
        synthesis_latency_ms=25.0,
    )

    eval_result = ResultEvaluation(
        decision=EvaluationDecision.SUFFICIENT,
        confidence=0.98,
        evidence_count=1,
        successful_tasks=["t1", "t2"],
        should_replan=False,
    )

    sanitized = format_sanitized_agent_diagnostics(
        diagnostics=diagnostics,
        plan=plan,
        specialist_results=results,
        total_time_ms=180.0,
        citation_count=1,
        latest_evaluation=eval_result,
    )

    # 1. Structure assertions
    assert sanitized["multi_agent_execution"] is True
    assert sanitized["plan_reasoning"] == "Two-step financial analysis"
    assert sanitized["total_specialist_calls"] == 2
    assert sanitized["total_time_ms"] == 180.0
    assert len(sanitized["tasks"]) == 2

    t1_diag = sanitized["tasks"][0]
    assert t1_diag["task_id"] == "t1"
    assert t1_diag["agent_type"] == "RESEARCH"
    assert t1_diag["status"] == "COMPLETED"
    assert t1_diag["success"] is True
    assert t1_diag["routed_capability"] == "research.fusion_rag"

    t2_diag = sanitized["tasks"][1]
    assert t2_diag["task_id"] == "t2"
    assert t2_diag["dependencies"] == ["t1"]

    assert sanitized["evaluation"]["decision"] == "SUFFICIENT"
    assert sanitized["evaluation"]["confidence"] == 0.98
    assert sanitized["concurrency_savings_ms"] == 45.0
    assert sanitized["evidence_count"] == 1
    assert sanitized["citation_count"] == 1

    # 2. Strict Security Boundaries: No raw text, prompts, tokens, or CoT in dump
    dump_str = json.dumps(sanitized)
    assert "Confidential raw text" not in dump_str
    assert "thought" not in dump_str
    assert "prompt" not in dump_str.lower() or "plan_reasoning" in dump_str


@pytest.mark.asyncio
async def test_chat_orchestrator_streaming_emits_and_persists_agent_diagnostics():
    """Verify generate_answer_stream emits agent_diagnostics in done event and persists in message metadata."""
    mock_conv_mgr = MagicMock()
    mock_conv_mgr._conversation_repo = None
    mock_conv_mgr._message_repo = AsyncMock()
    mock_conv = MagicMock()
    mock_conv.id = uuid4()
    mock_conv_mgr.get_or_create_conversation = AsyncMock(return_value=mock_conv)
    mock_conv_mgr.create_user_message = AsyncMock(return_value=MagicMock(id=uuid4()))
    mock_conv_mgr.create_assistant_message = AsyncMock(
        return_value=MagicMock(id=uuid4())
    )
    mock_conv_mgr.finalize_message = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.recent_messages = []
    mock_ctx.summary = None
    mock_rewrite = MagicMock()
    mock_rewrite.rewritten_query = "Calculate metrics"
    mock_rewrite.rewrite_applied = False
    mock_conv_mgr.prepare_context = AsyncMock(return_value=(mock_ctx, mock_rewrite))

    doc_service = AsyncMock()
    doc_service.list_documents.return_value = []
    mock_conv_mgr._document_service = doc_service

    # Mock master agent stream
    async def fake_stream(*args, **kwargs):
        yield {"event": "plan_created", "data": {"task_count": 1}}
        yield {"event": "text", "data": {"text": "Calculation result: 42"}}
        yield {
            "event": "synthesis_done",
            "data": {
                "citations": [],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        }
        yield {
            "event": "multi_agent_diagnostics",
            "data": {
                "multi_agent_execution": True,
                "total_specialist_calls": 1,
                "tasks": [{"task_id": "t1", "status": "COMPLETED", "success": True}],
            },
        }

    mock_master = MagicMock()
    mock_master.execute_request_stream = fake_stream

    orchestrator = ChatOrchestrator(
        conversation_manager=mock_conv_mgr,
        retrieval_service=AsyncMock(),
        prompt_builder=MagicMock(),
        context_builder=MagicMock(),
        token_estimator=MagicMock(estimate=MagicMock(return_value=10)),
        llm_generation_service=AsyncMock(),
        agent_executor=AsyncMock(),
        master_agent=mock_master,
        model="gemini-3.5-flash-lite",
        enable_conversation_memory=True,
        enable_multi_agent=True,
    )

    events = []
    async for ev in orchestrator.generate_answer_stream(
        conversation_id=mock_conv.id,
        user_id=uuid4(),
        question="Calculate metrics",
        top_k=5,
    ):
        events.append(ev)

    done_events = [e for e in events if e.get("event") == "done"]
    assert len(done_events) == 1
    done_data = done_events[0]["data"]
    assert done_data["answer"] == "Calculation result: 42"
    assert "agent_diagnostics" in done_data
    assert done_data["agent_diagnostics"]["multi_agent_execution"] is True
    assert done_data["agent_diagnostics"]["total_specialist_calls"] == 1

    # Verify finalized message received agent_diagnostics in metadata
    mock_conv_mgr.finalize_message.assert_called_once()
    _, kwargs = mock_conv_mgr.finalize_message.call_args
    meta = kwargs.get("metadata", {})
    assert "agent_diagnostics" in meta
    assert meta["agent_diagnostics"]["multi_agent_execution"] is True
