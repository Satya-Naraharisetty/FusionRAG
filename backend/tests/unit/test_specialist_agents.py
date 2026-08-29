from decimal import Decimal
from uuid import uuid4

import pytest

from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentTask,
    AgentType,
    ExecutionPlan,
)
from app.chat.services.multi_agent.plan_validator import (
    PlanValidationError,
    PlanValidator,
)
from app.chat.services.multi_agent.synthesis_agent import (
    CitationValidationStatus,
    CitationValidator,
    EvidenceAuthorizationGuard,
)
from app.chat.services.multi_agent.table_agent import TableAgent
from app.documents.domain.exceptions import UnauthorizedCapabilityError
from app.documents.domain.models import (
    AuthorizedDocumentScope,
    AuthorizedDocumentVersion,
    EvidenceItem,
    EvidenceType,
)
from app.documents.services.table_processor import TableProcessor


def test_table_processor_aggregation():
    processor = TableProcessor()
    markdown = """
    | Product | Q1 Sales | Q2 Sales |
    |---|---|---|
    | Widget A | 100.50 | 200.00 |
    | Widget B | 50.25 | 150.00 |
    | Widget C | -10.75 | 50.00 |
    """
    elem_id = uuid4()
    table = processor.parse_markdown_table(elem_id, markdown, title="Sales 2023")

    assert table.dimensions.row_count == 3
    assert table.dimensions.col_count == 3
    assert table.headers == ["Product", "Q1 Sales", "Q2 Sales"]

    sum_q1 = processor.execute_aggregation(table, "Q1 Sales", "SUM")
    assert sum_q1 == Decimal("140.00")

    avg_q2 = processor.execute_aggregation(table, "Q2 Sales", "AVG")
    assert avg_q2 == Decimal("133.3333333333333333333333333")

    max_q1 = processor.execute_aggregation(table, "Q1 Sales", "MAX")
    assert max_q1 == Decimal("100.50")

    min_q1 = processor.execute_aggregation(table, "Q1 Sales", "MIN")
    assert min_q1 == Decimal("-10.75")


@pytest.mark.asyncio
async def test_table_agent_execution():
    agent = TableAgent()
    user_id = uuid4()
    task = AgentTask(
        task_id="task_1",
        request="Calculate total sales",
        agent_type=AgentType.TABLE,
        parameters={
            "table_markdown": "| Item | Revenue |\n|---|---|\n| A | 100 |\n| B | 200 |",
            "operation": "SUM",
            "column_name": "Revenue",
        },
    )
    context = AgentExecutionContext(request_id="req_1", user_id=user_id)
    result = await agent.execute_task(task, context)

    assert result.success is True
    assert "Calculated SUM of 'Revenue': 300" in result.output
    assert len(result.evidence) == 1


def test_plan_validator_cycle_detection():
    validator = PlanValidator()
    # Cyclic plan: task_1 -> task_2 -> task_1
    task1 = AgentTask(
        task_id="task_1",
        request="Research 1",
        agent_type=AgentType.RESEARCH,
        dependencies=["task_2"],
    )
    task2 = AgentTask(
        task_id="task_2",
        request="Research 2",
        agent_type=AgentType.RESEARCH,
        dependencies=["task_1"],
    )
    plan = ExecutionPlan(request_id="req_1", tasks=[task1, task2])

    with pytest.raises(PlanValidationError, match="Cycle detected"):
        validator.validate(plan)


def test_plan_validator_forbidden_operation():
    validator = PlanValidator()
    task = AgentTask(
        task_id="task_1",
        request="Execute SQL",
        agent_type=AgentType.RESEARCH,
        parameters={"action": "execute_sql", "query": "DROP TABLE documents;"},
    )
    plan = ExecutionPlan(request_id="req_1", tasks=[task])

    with pytest.raises(
        UnauthorizedCapabilityError, match="Forbidden infrastructure action"
    ):
        validator.validate(plan)


@pytest.mark.asyncio
async def test_evidence_authorization_guard_and_citation_validator():
    guard = EvidenceAuthorizationGuard()
    validator = CitationValidator()

    user_id = uuid4()
    doc_id = uuid4()
    auth_version = 2

    scope = AuthorizedDocumentScope(
        user_id=user_id,
        authorized_docs={
            doc_id: AuthorizedDocumentVersion(
                active_version=auth_version,
                active_config_id=uuid4(),
                active_embedding_contract_id="contract_v1",
            )
        },
    )

    # Valid evidence item
    valid_ev = EvidenceItem(
        evidence_id=uuid4(),
        evidence_type=EvidenceType.TEXT_CHUNK,
        user_id=user_id,
        document_id=doc_id,
        document_version=auth_version,
        element_id=uuid4(),
        content="Revenue grew by 25% in Q3 2023.",
    )

    # Wrong version evidence item (stale v1)
    stale_ev = EvidenceItem(
        evidence_id=uuid4(),
        evidence_type=EvidenceType.TEXT_CHUNK,
        user_id=user_id,
        document_id=doc_id,
        document_version=1,
        element_id=uuid4(),
        content="Revenue grew by 25% in Q3 2023.",
    )

    # Guard checks
    assert guard.verify(valid_ev, scope) is True
    assert guard.verify(stale_ev, scope) is False

    # Validation check on valid evidence
    res_valid = await validator.validate(
        claim_text="Q3 2023 revenue increased by 25%",
        evidence_item=valid_ev,
        scope=scope,
        guard=guard,
    )
    assert res_valid.is_valid is True
    assert res_valid.status == CitationValidationStatus.ENTAILED

    # Validation check on stale evidence (must fail-closed)
    res_stale = await validator.validate(
        claim_text="Q3 2023 revenue increased by 25%",
        evidence_item=stale_ev,
        scope=scope,
        guard=guard,
    )
    assert res_stale.is_valid is False
    assert res_stale.status == CitationValidationStatus.INSUFFICIENT
