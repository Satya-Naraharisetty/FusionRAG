from uuid import uuid4

import pytest

from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentFailureReason,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
    EvidenceItem,
)
from app.chat.services.multi_agent.analysis_agent import AnalysisAgent


@pytest.fixture
def analysis_agent() -> AnalysisAgent:
    return AnalysisAgent()


@pytest.fixture
def empty_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        request_id="req-test-1",
        user_id=uuid4(),
        conversation_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_explicit_parameters_take_precedence(
    analysis_agent: AnalysisAgent, empty_context: AgentExecutionContext
):
    """Verify that when parameters are explicitly provided, they override any context text."""
    task = AgentTask(
        task_id="t1",
        request="Compute growth rate",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "growth_rate", "old_value": 50.0, "new_value": 100.0},
    )
    res = await analysis_agent.execute_task(task, empty_context)
    assert res.success is True
    assert res.status == AgentTaskStatus.COMPLETED
    assert res.metadata["growth_rate_pct"] == 100.0
    assert "Growth rate from 50.0 to 100.0: 100.00%" in res.output


@pytest.mark.asyncio
async def test_upstream_dependency_yearly_labeled_growth_rate(
    analysis_agent: AnalysisAgent,
):
    """Verify extraction of chronological yearly values (2022: $10M, 2023: $15M) for growth_rate."""
    ctx = AgentExecutionContext(
        request_id="req-2",
        user_id=uuid4(),
        conversation_id=uuid4(),
        dependency_results={
            "t_research": AgentResult(
                task_id="t_research",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Financial report summary",
                evidence=[
                    EvidenceItem(
                        chunk_id=uuid4(),
                        document_id=uuid4(),
                        document_name="annual_report.pdf",
                        content="In 2022: $10M in revenue was generated. By 2023: $15M was reported.",
                    )
                ],
            )
        },
    )
    task = AgentTask(
        task_id="t_calc",
        request="Calculate revenue growth rate from 2022 to 2023",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "growth_rate"},
        dependencies=["t_research"],
    )
    res = await analysis_agent.execute_task(task, ctx)
    assert res.success is True
    assert res.metadata["old_value"] == 10_000_000.0
    assert res.metadata["new_value"] == 15_000_000.0
    assert res.metadata["growth_rate_pct"] == 50.0


@pytest.mark.asyncio
async def test_upstream_dependency_baseline_target_percentage_change(
    analysis_agent: AnalysisAgent,
):
    """Verify baseline and target labeled extraction for percentage_change."""
    ctx = AgentExecutionContext(
        request_id="req-3",
        user_id=uuid4(),
        conversation_id=uuid4(),
        dependency_results={
            "dep1": AgentResult(
                task_id="dep1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Baseline: 200 units. Target: 300 units.",
            )
        },
    )
    task = AgentTask(
        task_id="t_pct",
        request="Calculate percentage change",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "percentage_change"},
    )
    res = await analysis_agent.execute_task(task, ctx)
    assert res.success is True
    assert res.metadata["base_value"] == 200.0
    assert res.metadata["target_value"] == 300.0
    assert res.metadata["percentage"] == 50.0


@pytest.mark.asyncio
async def test_scale_suffix_and_currency_parsing(analysis_agent: AnalysisAgent):
    """Verify handling of currency symbols (€, £, $) and scale suffixes (k, million, billion)."""
    assert analysis_agent._parse_numeric_value("$10M") == 10_000_000.0
    assert analysis_agent._parse_numeric_value("€15.5 million") == 15_500_000.0
    assert analysis_agent._parse_numeric_value("£250k") == 250_000.0
    assert analysis_agent._parse_numeric_value("2.5 billion") == 2_500_000_000.0
    assert analysis_agent._parse_numeric_value("1,500") == 1500.0


@pytest.mark.asyncio
async def test_sum_and_average_from_upstream_evidence(analysis_agent: AnalysisAgent):
    """Verify sum and average over extracted labeled items."""
    ctx = AgentExecutionContext(
        request_id="req-4",
        user_id=uuid4(),
        conversation_id=uuid4(),
        dependency_results={
            "r1": AgentResult(
                task_id="r1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Q1: 10, Q2: 20, Q3: 30",
            )
        },
    )
    # Sum
    task_sum = AgentTask(
        task_id="t_sum",
        request="Compute sum of quarterly revenues",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "sum"},
    )
    res_sum = await analysis_agent.execute_task(task_sum, ctx)
    assert res_sum.success is True
    assert res_sum.metadata["total"] == 60.0

    # Average
    task_avg = AgentTask(
        task_id="t_avg",
        request="Compute average quarterly revenue",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "average"},
    )
    res_avg = await analysis_agent.execute_task(task_avg, ctx)
    assert res_avg.success is True
    assert res_avg.metadata["average"] == 20.0


@pytest.mark.asyncio
async def test_difference_from_from_to_pattern(analysis_agent: AnalysisAgent):
    """Verify difference calculation from 'from X to Y' pattern."""
    ctx = AgentExecutionContext(
        request_id="req-5",
        user_id=uuid4(),
        conversation_id=uuid4(),
        dependency_results={
            "r1": AgentResult(
                task_id="r1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="Revenue increased from $80M to $120M.",
            )
        },
    )
    task_diff = AgentTask(
        task_id="t_diff",
        request="Calculate difference",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "difference"},
    )
    res_diff = await analysis_agent.execute_task(task_diff, ctx)
    assert res_diff.success is True
    assert res_diff.metadata["val1"] == 80_000_000.0
    assert res_diff.metadata["val2"] == 120_000_000.0
    assert res_diff.metadata["difference"] == -40_000_000.0


@pytest.mark.asyncio
async def test_missing_numeric_evidence_fails_safely(
    analysis_agent: AnalysisAgent, empty_context: AgentExecutionContext
):
    """Verify missing numeric evidence fails safely with VALIDATION_ERROR rather than crashing."""
    task = AgentTask(
        task_id="t_fail",
        request="Calculate growth rate",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "growth_rate"},
    )
    res = await analysis_agent.execute_task(task, empty_context)
    assert res.success is False
    assert res.status == AgentTaskStatus.FAILED
    assert res.failure_reason == AgentFailureReason.VALIDATION_ERROR
    assert "Missing numeric values" in res.error


@pytest.mark.asyncio
async def test_ambiguous_conflicting_evidence_fails_safely(
    analysis_agent: AnalysisAgent,
):
    """Verify multiple conflicting numbers with no clear ordering fail safely."""
    ctx = AgentExecutionContext(
        request_id="req-6",
        user_id=uuid4(),
        conversation_id=uuid4(),
        dependency_results={
            "r1": AgentResult(
                task_id="r1",
                agent_type=AgentType.RESEARCH,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output="sales: 10, profit: 25, expenses: 40, tax: 5",
            )
        },
    )
    task = AgentTask(
        task_id="t_ambig",
        request="Calculate growth rate",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "growth_rate"},
    )
    res = await analysis_agent.execute_task(task, ctx)
    assert res.success is False
    assert res.status == AgentTaskStatus.FAILED
    assert res.failure_reason == AgentFailureReason.VALIDATION_ERROR
    assert "Ambiguous numeric evidence" in res.error


@pytest.mark.asyncio
async def test_sandboxing_blocks_unsafe_code_and_arbitrary_expressions(
    analysis_agent: AnalysisAgent, empty_context: AgentExecutionContext
):
    """Verify that arbitrary code or dangerous builtins cannot be executed."""
    task = AgentTask(
        task_id="t_unsafe",
        request="Calculate expression",
        agent_type=AgentType.ANALYSIS,
        parameters={"expression": "__import__('os').system('ls')"},
    )
    res = await analysis_agent.execute_task(task, empty_context)
    assert res.success is False
    assert res.status == AgentTaskStatus.FAILED
    assert "Disallowed AST node" in res.error or "error" in res.error.lower()
