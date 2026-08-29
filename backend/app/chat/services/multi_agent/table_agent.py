import time
from uuid import UUID

from app.chat.domain.models import Citation
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
    EvidenceItem,
)
from app.chat.services.multi_agent.base import BaseSpecialistAgent
from app.documents.services.table_processor import TableProcessor


class TableAgent(BaseSpecialistAgent):
    """
    Specialist agent for structured tabular data extraction, aggregation,
    and deterministic arithmetic evaluation.
    """

    agent_type = AgentType.TABLE

    def __init__(self, table_processor: TableProcessor | None = None) -> None:
        self.table_processor = table_processor or TableProcessor()

    async def execute_task(
        self, task: AgentTask, context: AgentExecutionContext
    ) -> AgentResult:
        t0 = time.perf_counter()
        query = task.request
        table_raw = (
            task.parameters.get("table_markdown")
            or task.parameters.get("table_csv")
            or ""
        )
        operation = task.parameters.get("operation")
        column_name = task.parameters.get("column_name")

        evidence_items: list[EvidenceItem] = []
        citations: list[Citation] = []
        output_text = ""

        if table_raw:
            dummy_elem_id = UUID("00000000-0000-0000-0000-000000000000")
            if task.parameters.get("table_csv"):
                parsed_table = self.table_processor.parse_csv_table(
                    dummy_elem_id, table_raw
                )
            else:
                parsed_table = self.table_processor.parse_markdown_table(
                    dummy_elem_id, table_raw
                )

            if operation and column_name:
                agg_result = self.table_processor.execute_aggregation(
                    parsed_table, column_name=column_name, operation=operation
                )
                if agg_result is not None:
                    output_text = (
                        f"Calculated {operation} of '{column_name}': {agg_result}"
                    )
                else:
                    output_text = (
                        f"Could not compute {operation} on column '{column_name}'."
                    )
            else:
                output_text = f"Table summary: {parsed_table.summary}\n\n{self.table_processor.to_markdown(parsed_table)}"

            ev = EvidenceItem(
                document_name="Structured Table",
                content=output_text,
                score=1.0,
                metadata={
                    "table_headers": parsed_table.headers,
                    "dimensions": f"{parsed_table.dimensions.row_count}x{parsed_table.dimensions.col_count}",
                },
            )
            evidence_items.append(ev)
        else:
            output_text = f"Executed table analysis for query: '{query}'"

        dur_ms = (time.perf_counter() - t0) * 1000.0

        return AgentResult(
            task_id=task.task_id,
            agent_type=self.agent_type,
            status=AgentTaskStatus.COMPLETED,
            success=True,
            output=output_text,
            evidence=evidence_items,
            citations=citations,
            execution_time_ms=dur_ms,
        )
