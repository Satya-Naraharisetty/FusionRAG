import pytest
from uuid import uuid4

from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentTask,
    AgentTaskStatus,
    AgentType,
)
from app.chat.services.multi_agent.analysis_agent import AnalysisAgent


@pytest.mark.asyncio
async def test_analysis_agent_solves_algebraic_task():
    agent = AnalysisAgent()
    task = AgentTask(
        task_id="task_alg_1",
        request="Solve the equation 3*x + 9 = 24 for x",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "solve_equation", "equation": "3*x + 9 = 24", "variable": "x"},
    )
    context = AgentExecutionContext(
        request_id=str(uuid4()),
        user_id=uuid4(),
        conversation_id=uuid4(),
    )

    res = await agent.execute_task(task, context)
    assert res.success is True
    assert res.status == AgentTaskStatus.COMPLETED
    assert "5" in str(res.metadata.get("solutions"))
    assert "$$" in res.output


@pytest.mark.asyncio
async def test_analysis_agent_solves_ode_task():
    agent = AnalysisAgent()
    task = AgentTask(
        task_id="task_ode_1",
        request="Solve the differential equation y'' + 4y = 0",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "solve_ode", "ode": "Derivative(y(x), x, 2) + 4*y(x)"},
    )
    context = AgentExecutionContext(
        request_id=str(uuid4()),
        user_id=uuid4(),
        conversation_id=uuid4(),
    )

    res = await agent.execute_task(task, context)
    assert res.success is True
    assert "sin" in res.output and "cos" in res.output
    assert "sin(2*x)" in res.metadata["solution"]


@pytest.mark.asyncio
async def test_analysis_agent_computes_cagr_task():
    agent = AnalysisAgent()
    task = AgentTask(
        task_id="task_cagr_1",
        request="Calculate CAGR from $50,000 to $120,000 over 4 years",
        agent_type=AgentType.ANALYSIS,
        parameters={"operation": "cagr", "beginning_value": 50000, "ending_value": 120000, "periods": 4},
    )
    context = AgentExecutionContext(
        request_id=str(uuid4()),
        user_id=uuid4(),
        conversation_id=uuid4(),
    )

    res = await agent.execute_task(task, context)
    assert res.success is True
    assert res.metadata["cagr_percent"] > 0
    assert "24.47" in res.output
