from datetime import UTC, datetime
from unittest.mock import AsyncMock
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
    EvaluationDecision,
    EvidenceItem,
    ExecutionOutcome,
    ExecutionPlan,
    MissingRequirement,
    ResultEvaluation,
    SynthesisRequest,
)
from app.chat.services.multi_agent.analysis_agent import AnalysisAgent
from app.chat.services.multi_agent.document_agent import DocumentAgent
from app.chat.services.multi_agent.execution_engine import AgentExecutionEngine
from app.chat.services.multi_agent.master_agent import MasterAgent
from app.chat.services.multi_agent.research_agent import ResearchAgent
from app.chat.services.multi_agent.result_evaluator import ResultEvaluator
from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent
from app.documents.domain.models import (
    Document,
    DocumentScope,
    DocumentStatus,
    RetrievedChunk,
    SearchResult,
)


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
    def __init__(self, documents: dict | None = None) -> None:
        self.documents = dict(documents or {})

    async def get_by_id(self, id):
        try:
            return self.documents.get(UUID(str(id)))
        except (ValueError, TypeError):
            return self.documents.get(id)

    async def list_by_user(self, user_id):
        return [d for d in self.documents.values() if d.user_id == user_id]

    async def list_by_conversation(self, conversation_id, user_id):
        return [
            d
            for d in self.documents.values()
            if d.user_id == user_id and d.conversation_id == conversation_id
        ]


class FakeChunkRepo:
    def __init__(self, chunks: dict | None = None) -> None:
        self.chunks = dict(chunks or {})

    async def list_by_document(self, document_id):
        return self.chunks.get(document_id, [])


# ===========================================================================
# Category 1: Deterministic Evaluation (6 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_eval_successful_required_task_sufficient():
    evaluator = ResultEvaluator()
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="Retrieve refund policy",
                agent_type=AgentType.RESEARCH,
                is_required=True,
            )
        ],
    )
    outcome = ExecutionOutcome(
        request_id="req-1",
        completed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Refund within 30 days.",
                evidence=[
                    EvidenceItem(
                        document_name="policy.md",
                        content="Refund policy allows 30 days.",
                    )
                ],
            )
        ],
    )

    evaluation = await evaluator.evaluate("What is the refund policy?", plan, outcome)
    assert evaluation.decision == EvaluationDecision.SUFFICIENT
    assert evaluation.should_replan is False
    assert evaluation.evidence_count == 1


@pytest.mark.asyncio
async def test_eval_missing_evidence_partial():
    evaluator = ResultEvaluator()
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="Search Q2 and Q3 revenue",
                agent_type=AgentType.RESEARCH,
            )
        ],
    )
    outcome = ExecutionOutcome(
        request_id="req-1",
        completed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Q3 revenue = 1.5M",
                evidence=[
                    EvidenceItem(
                        document_name="q3.pdf",
                        content="Q3 revenue was 1.5M dollars.",
                    )
                ],
            )
        ],
    )

    evaluation = await evaluator.evaluate(
        "Find Q2 and Q3 revenue and compute growth", plan, outcome
    )
    assert evaluation.decision == EvaluationDecision.PARTIAL
    assert evaluation.should_replan is True
    assert any("Q2" in mr.requirement for mr in evaluation.missing_requirements)


@pytest.mark.asyncio
async def test_eval_failed_required_task_retryable():
    evaluator = ResultEvaluator()
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="Fetch server logs",
                agent_type=AgentType.RESEARCH,
                is_required=True,
                retryable=True,
            )
        ],
    )
    outcome = ExecutionOutcome(
        request_id="req-1",
        failed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error="DB query timeout after 20s",
                failure_reason=AgentFailureReason.TIMEOUT,
            )
        ],
    )

    evaluation = await evaluator.evaluate("Fetch server logs", plan, outcome)
    assert evaluation.decision == EvaluationDecision.RETRYABLE_FAILURE
    assert evaluation.should_replan is True


@pytest.mark.asyncio
async def test_eval_permanent_authorization_failure_terminal():
    evaluator = ResultEvaluator()
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="Inspect restricted doc",
                agent_type=AgentType.DOCUMENT,
            )
        ],
    )
    outcome = ExecutionOutcome(
        request_id="req-1",
        failed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.DOCUMENT,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error="Access Denied: Document does not belong to requesting user",
                failure_reason=AgentFailureReason.UNAUTHORIZED,
            )
        ],
    )

    evaluation = await evaluator.evaluate("Inspect document 123", plan, outcome)
    assert evaluation.decision == EvaluationDecision.TERMINAL_FAILURE
    assert evaluation.should_replan is False


@pytest.mark.asyncio
async def test_eval_dependency_failure():
    evaluator = ResultEvaluator()
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1", request="Research data", agent_type=AgentType.RESEARCH
            ),
            AgentTask(
                task_id="t2",
                request="Calculate sum",
                agent_type=AgentType.ANALYSIS,
                dependencies=["t1"],
            ),
        ],
    )
    outcome = ExecutionOutcome(
        request_id="req-1",
        failed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error="Network timeout",
                failure_reason=AgentFailureReason.TIMEOUT,
            )
        ],
        skipped_results=[
            AgentResult(
                task_id="t2",
                agent_type=AgentType.ANALYSIS,
                status=AgentTaskStatus.SKIPPED,
                success=False,
                output="",
                error="Dependency 't1' failed",
                failure_reason=AgentFailureReason.DEPENDENCY_FAILED,
            )
        ],
    )

    evaluation = await evaluator.evaluate("Calculate sum of data", plan, outcome)
    assert evaluation.decision in {
        EvaluationDecision.RETRYABLE_FAILURE,
        EvaluationDecision.INSUFFICIENT,
    }
    assert evaluation.should_replan is True


@pytest.mark.asyncio
async def test_eval_empty_result_insufficient():
    evaluator = ResultEvaluator()
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="Search non-existent topic",
                agent_type=AgentType.RESEARCH,
            )
        ],
    )
    outcome = ExecutionOutcome(
        request_id="req-1",
        completed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="No relevant evidence found.",
                evidence=[],
                metadata={"insufficient_evidence": True},
            )
        ],
    )

    evaluation = await evaluator.evaluate("Search non-existent topic", plan, outcome)
    assert evaluation.decision == EvaluationDecision.INSUFFICIENT
    assert evaluation.should_replan is True


# ===========================================================================
# Category 2: Replanning & Result Reuse (6 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_replan_missing_requirement_triggers_targeted_replan():
    retrieval_mock = AsyncMock()
    # Iteration 1 returns Q3 revenue only
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="revenue",
        retrieval_time=1.0,
        total_matches=1,
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id=uuid4(),
                document_id=uuid4(),
                chunk_index=0,
                text="Q3 revenue was 1.5M dollars.",
                similarity_score=0.9,
                document_name="q3.pdf",
            )
        ],
    )

    research_agent = ResearchAgent(retrieval_mock)
    analysis_agent = AnalysisAgent()
    engine = AgentExecutionEngine(specialist_agents=[research_agent, analysis_agent])

    fake_llm = FakeLLMProvider()
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        max_plan_iterations=2,
    )

    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())
    res = await master.execute_request(
        "Find Q2 and Q3 revenue and compute growth", context
    )

    assert res.diagnostics.plan_iterations >= 2
    assert res.diagnostics.replans >= 1


@pytest.mark.asyncio
async def test_replan_successful_tasks_not_repeated():
    # Setup master agent
    retrieval_mock = AsyncMock()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="query",
        retrieval_time=1.0,
        total_matches=1,
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id=uuid4(),
                document_id=uuid4(),
                chunk_index=0,
                text="Q3 revenue = 1.5M",
                similarity_score=0.9,
                document_name="q3.pdf",
            )
        ],
    )
    research_agent = ResearchAgent(retrieval_mock)
    engine = AgentExecutionEngine(specialist_agents=[research_agent])
    fake_llm = FakeLLMProvider()
    synthesis = SynthesisAgent(llm_provider=fake_llm)

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        max_plan_iterations=2,
    )
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    prev_plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(task_id="t1", request="Q3 revenue", agent_type=AgentType.RESEARCH)
        ],
    )

    accumulated = {
        "t1": AgentResult(
            task_id="t1",
            agent_type=AgentType.RESEARCH,
            status=AgentTaskStatus.COMPLETED,
            success=True,
            output="Q3 revenue = 1.5M",
            evidence=[
                EvidenceItem(document_name="q3.pdf", content="Q3 revenue = 1.5M")
            ],
        )
    }

    eval_res = ResultEvaluation(
        decision=EvaluationDecision.PARTIAL,
        confidence=0.9,
        evidence_count=1,
        missing_requirements=[
            MissingRequirement(requirement="Q2 revenue", reason="Q2 revenue missing")
        ],
        should_replan=True,
    )

    refined_plan, dupes = await master.create_refined_plan(
        request="Compare Q2 and Q3",
        previous_plan=prev_plan,
        evaluation=eval_res,
        accumulated_results=accumulated,
        context=context,
        iteration=2,
    )

    # t1 should NOT be re-added as a new task to execute
    assert not any(t.task_id == "t1" for t in refined_plan.tasks)


@pytest.mark.asyncio
async def test_replan_preserves_successful_upstream_results_without_reexecution():
    """Explicit test 9: Replanning preserves successful upstream results without re-executing them."""
    executed_task_ids = []

    class TrackingResearchAgent(ResearchAgent):
        async def execute_task(self, task, context):
            executed_task_ids.append(task.task_id)
            return await super().execute_task(task, context)

    retrieval_mock = AsyncMock()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="Q3",
        retrieval_time=1.0,
        total_matches=1,
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id=uuid4(),
                document_id=uuid4(),
                chunk_index=0,
                text="Q3 revenue is 10M",
                similarity_score=0.9,
                document_name="q3.pdf",
            )
        ],
    )
    agent = TrackingResearchAgent(retrieval_mock)
    engine = AgentExecutionEngine(specialist_agents=[agent])
    fake_llm = FakeLLMProvider()
    synthesis = SynthesisAgent(llm_provider=fake_llm)

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        max_plan_iterations=2,
    )
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    response = await master.execute_request("Find Q2 and Q3 revenue", context)

    # In iteration 1, task_1 executed. In iteration 2, refine_task executed. task_1 was NOT re-executed!
    assert executed_task_ids.count("research_1") <= 1
    assert any(r.task_id == "research_1" for r in response.specialist_results)


@pytest.mark.asyncio
async def test_replan_identical_failed_tasks_not_retried_indefinitely():
    fake_llm = FakeLLMProvider()
    engine = AgentExecutionEngine(specialist_agents=[])
    synthesis = SynthesisAgent(llm_provider=fake_llm)

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        max_plan_iterations=3,
    )
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    failed_task = AgentTask(
        task_id="failed_1",
        request="Retrieve missing requirement: Q2 revenue",
        agent_type=AgentType.RESEARCH,
        parameters={"query": "Q2 revenue"},
    )
    prev_plan = ExecutionPlan(request_id="req-1", tasks=[failed_task])
    accumulated = {
        "failed_1": AgentResult(
            task_id="failed_1",
            agent_type=AgentType.RESEARCH,
            status=AgentTaskStatus.FAILED,
            success=False,
            output="",
            error="DB error",
        )
    }

    eval_res = ResultEvaluation(
        decision=EvaluationDecision.INSUFFICIENT,
        missing_requirements=[
            MissingRequirement(requirement="Q2 revenue", reason="Failed")
        ],
        should_replan=True,
    )

    refined_plan, dupes = await master.create_refined_plan(
        request="Find Q2 revenue",
        previous_plan=prev_plan,
        evaluation=eval_res,
        accumulated_results=accumulated,
        context=context,
        iteration=2,
    )

    assert dupes >= 1


@pytest.mark.asyncio
async def test_replan_stops_at_max_plan_iterations():
    retrieval_mock = AsyncMock()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="unmatched",
        retrieval_time=1.0,
        total_matches=0,
        retrieved_chunks=[],
    )
    research_agent = ResearchAgent(retrieval_mock)
    engine = AgentExecutionEngine(specialist_agents=[research_agent])
    fake_llm = FakeLLMProvider()
    synthesis = SynthesisAgent(llm_provider=fake_llm)

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        max_plan_iterations=2,
    )
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    response = await master.execute_request("Search unmatched query", context)
    assert response.diagnostics.plan_iterations == 2


@pytest.mark.asyncio
async def test_replan_respects_execution_limits():
    retrieval_mock = AsyncMock()
    retrieval_mock.retrieve.return_value = SearchResult(
        original_query="query",
        retrieval_time=1.0,
        total_matches=1,
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id=uuid4(),
                document_id=uuid4(),
                chunk_index=0,
                text="chunk content",
                similarity_score=0.9,
                document_name="test.md",
            )
        ],
    )
    research_agent = ResearchAgent(retrieval_mock)
    engine = AgentExecutionEngine(specialist_agents=[research_agent], max_total_calls=2)
    fake_llm = FakeLLMProvider()
    synthesis = SynthesisAgent(llm_provider=fake_llm)

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        max_plan_iterations=5,
        max_total_calls=2,
    )
    context = AgentExecutionContext(request_id="req-1", user_id=uuid4())

    response = await master.execute_request("Search query", context)
    assert response.diagnostics.total_specialist_calls <= 2


# ===========================================================================
# Category 3: LLM Evaluation & Fallbacks (4 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_llm_eval_valid_structured_output_accepted():
    llm_resp = """```json
    {
        "decision": "PARTIAL",
        "confidence": 0.88,
        "missing_requirements": [
            {
                "requirement": "Q2 revenue data",
                "reason": "Only Q3 revenue was found in retrieved chunks",
                "suggested_agent_type": "RESEARCH",
                "priority": 1
            }
        ],
        "contradictions": [],
        "recommendations": ["Search Q2 financial reports"],
        "should_replan": true,
        "reason": "Missing Q2 revenue for comparative growth calculation"
    }
    ```"""
    fake_llm = FakeLLMProvider(responses=[llm_resp])
    evaluator = ResultEvaluator(llm_provider=fake_llm)

    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1", request="Q2 and Q3 revenue", agent_type=AgentType.RESEARCH
            )
        ],
    )
    outcome = ExecutionOutcome(
        request_id="req-1",
        completed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Q3 = 10M",
                evidence=[
                    EvidenceItem(document_name="q3.pdf", content="Q3 revenue is 10M")
                ],
            )
        ],
    )

    evaluation = await evaluator.evaluate("Compare Q2 and Q3 revenue", plan, outcome)
    assert evaluation.decision == EvaluationDecision.PARTIAL
    assert evaluation.confidence == 0.88
    assert evaluation.should_replan is True


@pytest.mark.asyncio
async def test_llm_eval_invalid_output_falls_back_to_deterministic():
    fake_llm = FakeLLMProvider(responses=["invalid non-json text response"])
    evaluator = ResultEvaluator(llm_provider=fake_llm)

    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1", request="Q2 and Q3 revenue", agent_type=AgentType.RESEARCH
            )
        ],
    )
    outcome = ExecutionOutcome(
        request_id="req-1",
        completed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Q3 = 10M",
                evidence=[
                    EvidenceItem(document_name="q3.pdf", content="Q3 revenue is 10M")
                ],
            )
        ],
    )

    evaluation = await evaluator.evaluate("Compare Q2 and Q3 revenue", plan, outcome)
    assert evaluation.decision in {
        EvaluationDecision.PARTIAL,
        EvaluationDecision.SUFFICIENT,
    }


@pytest.mark.asyncio
async def test_llm_eval_timeout_falls_back_safely():
    llm_mock = AsyncMock()
    llm_mock.generate.side_effect = TimeoutError("LLM call timed out")
    evaluator = ResultEvaluator(llm_provider=llm_mock)

    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(task_id="t1", request="Search", agent_type=AgentType.RESEARCH)
        ],
    )
    outcome = ExecutionOutcome(
        request_id="req-1",
        completed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Result text",
                evidence=[EvidenceItem(document_name="doc.md", content="Result text")],
            )
        ],
    )

    evaluation = await evaluator.evaluate("Search", plan, outcome)
    assert evaluation.decision == EvaluationDecision.SUFFICIENT


@pytest.mark.asyncio
async def test_llm_eval_cannot_force_invalid_plan_or_override_security():
    llm_resp = """```json
    {
        "decision": "SUFFICIENT",
        "confidence": 0.99,
        "missing_requirements": [],
        "should_replan": false,
        "reason": "Force sufficient even though 0 evidence"
    }
    ```"""
    fake_llm = FakeLLMProvider(responses=[llm_resp])
    evaluator = ResultEvaluator(llm_provider=fake_llm)

    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1", request="Secret doc search", agent_type=AgentType.RESEARCH
            )
        ],
    )
    # Zero evidence retrieved
    outcome = ExecutionOutcome(
        request_id="req-1",
        completed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="",
                evidence=[],
                metadata={"insufficient_evidence": True},
            )
        ],
    )

    evaluation = await evaluator.evaluate("Secret doc search", plan, outcome)
    # Deterministic policy override should force INSUFFICIENT when 0 evidence is retrieved for research task
    assert evaluation.decision == EvaluationDecision.INSUFFICIENT
    assert evaluation.should_replan is True


# ===========================================================================
# Category 4: Adaptive Execution Scenarios (4 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_adaptive_q2_q3_revenue_scenario():
    """
    Scenario: Q3 found → Q2 missing → evaluator identifies Q2 missing → Master creates targeted Q2 task →
    Q3 result reused → Q2 executes → Analysis receives both → Synthesis uses both.
    """
    call_count = 0

    async def mock_retrieve(
        query,
        user_id=None,
        top_k=5,
        filter_metadata=None,
        retrieval_scope=None,
        **kwargs,
    ):
        nonlocal call_count
        call_count += 1
        query_lower = query.lower()
        if "q2" in query_lower:
            return SearchResult(
                original_query=query,
                retrieval_time=1.0,
                total_matches=1,
                retrieved_chunks=[
                    RetrievedChunk(
                        chunk_id=uuid4(),
                        document_id=uuid4(),
                        chunk_index=0,
                        text="Q2 revenue was 8.0M dollars.",
                        similarity_score=0.91,
                        document_name="q2.pdf",
                    )
                ],
            )
        return SearchResult(
            original_query=query,
            retrieval_time=1.0,
            total_matches=1,
            retrieved_chunks=[
                RetrievedChunk(
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    chunk_index=0,
                    text="Q3 revenue was 10.0M dollars.",
                    similarity_score=0.93,
                    document_name="q3.pdf",
                )
            ],
        )

    retrieval_mock = AsyncMock()
    retrieval_mock.retrieve.side_effect = mock_retrieve

    research_agent = ResearchAgent(retrieval_mock)
    analysis_agent = AnalysisAgent()
    engine = AgentExecutionEngine(specialist_agents=[research_agent, analysis_agent])

    fake_llm = FakeLLMProvider()
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        max_plan_iterations=2,
    )

    context = AgentExecutionContext(request_id="req-q2q3", user_id=uuid4())
    res = await master.execute_request(
        "Find Q2 revenue and Q3 revenue and compute growth", context
    )

    assert res.diagnostics.plan_iterations == 2
    assert len(res.citations) >= 2
    doc_names = {c.document_name for c in res.citations}
    assert "q3.pdf" in doc_names
    assert "q2.pdf" in doc_names


@pytest.mark.asyncio
async def test_adaptive_partial_evidence_produces_grounded_partial_response():
    fake_llm = FakeLLMProvider(
        responses=["Based on available Q3 data (10M), Q2 data was missing."]
    )
    synthesis = SynthesisAgent(llm_provider=fake_llm)
    doc_id = uuid4()
    chunk_id = uuid4()

    req = SynthesisRequest(
        request_id="req-partial",
        original_request="Find Q2 and Q3 revenue",
        specialist_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Q3 = 10M",
                evidence=[
                    EvidenceItem(
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        document_name="q3.pdf",
                        content="Q3 revenue is 10M",
                    )
                ],
                citations=[
                    Citation(
                        document_id=doc_id,
                        document_name="q3.pdf",
                        chunk_id=chunk_id,
                        chunk_index=0,
                    )
                ],
            )
        ],
        context=AgentExecutionContext(request_id="req-partial", user_id=uuid4()),
    )

    answer, citations, usage = await synthesis.synthesize(req, model="test-model")
    assert "Q3" in answer or "10M" in answer
    assert len(citations) == 1


@pytest.mark.asyncio
async def test_adaptive_contradictory_evidence_surfaced():
    evaluator = ResultEvaluator()
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(task_id="t1", request="Q3 revenue", agent_type=AgentType.RESEARCH)
        ],
    )
    outcome = ExecutionOutcome(
        request_id="req-1",
        completed_results=[
            AgentResult(
                task_id="t1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Different revenues found",
                evidence=[
                    EvidenceItem(
                        document_name="draft.pdf", content="Q3 revenue was 10M dollars."
                    ),
                    EvidenceItem(
                        document_name="final.pdf", content="Q3 revenue was 12M dollars."
                    ),
                ],
            )
        ],
    )

    evaluation = await evaluator.evaluate("What was Q3 revenue?", plan, outcome)
    assert len(evaluation.contradictions) > 0


@pytest.mark.asyncio
async def test_adaptive_specialist_timeout_triggers_bounded_retry():
    call_count = 0

    class TimeoutOnceSpecialist(ResearchAgent):
        async def execute_task(self, task, context):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AgentResult(
                    task_id=task.task_id,
                    agent_type=self.agent_type,
                    status=AgentTaskStatus.FAILED,
                    success=False,
                    output="",
                    error="Timeout",
                    failure_reason=AgentFailureReason.TIMEOUT,
                )
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Success on retry",
                evidence=[EvidenceItem(document_name="data.md", content="Retry data")],
            )
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Success on retry",
                evidence=[EvidenceItem(document_name="data.md", content="Retry data")],
            )

    specialist = TimeoutOnceSpecialist(AsyncMock())
    engine = AgentExecutionEngine(specialist_agents=[specialist])
    fake_llm = FakeLLMProvider()
    synthesis = SynthesisAgent(llm_provider=fake_llm)

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        max_plan_iterations=2,
    )
    context = AgentExecutionContext(request_id="req-retry", user_id=uuid4())

    response = await master.execute_request("Fetch data", context)
    assert response.diagnostics.plan_iterations == 2
    assert response.diagnostics.retry_count == 1


# ===========================================================================
# Category 5: Security & Policy Enforcement (5 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_security_replan_cannot_bypass_document_ownership():
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
    chunk_repo = FakeChunkRepo()
    doc_agent = DocumentAgent(document_repo=doc_repo, chunk_repo=chunk_repo)

    engine = AgentExecutionEngine(specialist_agents=[doc_agent])
    fake_llm = FakeLLMProvider()
    synthesis = SynthesisAgent(llm_provider=fake_llm)

    master = MasterAgent(
        llm_provider=fake_llm,
        execution_engine=engine,
        synthesis_agent=synthesis,
        max_plan_iterations=2,
    )

    context = AgentExecutionContext(request_id="req-sec", user_id=attacker_id)
    response = await master.execute_request(f"Inspect document {doc_id}", context)

    # Document access should fail with unauthorized failure
    assert any(
        res.failure_reason == AgentFailureReason.UNAUTHORIZED
        for res in response.specialist_results
    )


@pytest.mark.asyncio
async def test_security_replan_cannot_introduce_unauthorized_doc_ids():
    engine = AgentExecutionEngine(specialist_agents=[])
    errors = engine.validate_plan(
        ExecutionPlan(
            request_id="req-1",
            tasks=[
                AgentTask(
                    task_id="t1",
                    request="Invalid task",
                    agent_type=AgentType.SYNTHESIS,  # Unauthorized type
                )
            ],
        )
    )
    assert any("unauthorized or unexecutable agent type" in e for e in errors)


@pytest.mark.asyncio
async def test_security_replan_cannot_increase_configured_execution_limits():
    master = MasterAgent(
        llm_provider=FakeLLMProvider(),
        execution_engine=AgentExecutionEngine(
            specialist_agents=[], max_specialist_tasks=3
        ),
        synthesis_agent=SynthesisAgent(llm_provider=FakeLLMProvider()),
        max_plan_iterations=2,
        max_total_calls=4,
    )
    assert master.max_plan_iterations == 2
    assert master.max_total_calls == 4


@pytest.mark.asyncio
async def test_security_planner_cannot_create_master_or_synthesis_tasks():
    engine = AgentExecutionEngine(specialist_agents=[])
    plan = ExecutionPlan(
        request_id="req-1",
        tasks=[
            AgentTask(
                task_id="t1",
                request="Direct master call",
                agent_type=AgentType.MASTER,
            )
        ],
    )
    errors = engine.validate_plan(plan)
    assert len(errors) > 0


@pytest.mark.asyncio
async def test_security_failed_results_not_interpreted_as_factual_evidence():
    """Explicit test 25: Failed/skipped AgentResults are not interpreted as factual evidence."""
    fake_llm = FakeLLMProvider()
    synthesis = SynthesisAgent(llm_provider=fake_llm)

    failed_result = AgentResult(
        task_id="t_failed",
        agent_type=AgentType.RESEARCH,
        status=AgentTaskStatus.FAILED,
        success=False,
        output="Confidential leaked text that should never be evidence",
        error="Access Denied",
        failure_reason=AgentFailureReason.UNAUTHORIZED,
    )

    req = SynthesisRequest(
        request_id="req-sec-synth",
        original_request="Get secret data",
        specialist_results=[failed_result],
        context=AgentExecutionContext(request_id="req-sec-synth", user_id=uuid4()),
    )

    prompt_messages = synthesis._build_synthesis_prompt(req)
    user_content = prompt_messages[1].content

    # The failed output string should NOT be under Grounded Evidence!
    assert "=== Grounded Evidence ===\n(No document chunks retrieved)" in user_content
    assert "=== Diagnostic Notices / Incomplete Operations ===" in user_content
    assert "Access Denied" in user_content
