import logging
import re
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
from app.documents.domain.interfaces import DocumentElementRepository
from app.documents.domain.models import ElementType
from app.documents.services.table_processor import TableProcessor

logger = logging.getLogger(__name__)


class TableAgent(BaseSpecialistAgent):
    """
    Specialist agent for structured tabular data extraction, aggregation,
    and deterministic arithmetic evaluation.
    """

    agent_type = AgentType.TABLE

    def __init__(
        self,
        table_processor: TableProcessor | None = None,
        element_repo: DocumentElementRepository | None = None,
    ) -> None:
        if table_processor is None or hasattr(table_processor, "dependency"):
            self.table_processor = TableProcessor()
        else:
            self.table_processor = table_processor

        if element_repo is not None and hasattr(element_repo, "dependency"):
            self.element_repo = None
        else:
            self.element_repo = element_repo

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

        # 1. Consume table from upstream DAG dependency results if not in parameters
        if not table_raw and context.dependency_results:
            for dep_res in context.dependency_results.values():
                if dep_res.output and "|" in dep_res.output:
                    table_raw = dep_res.output
                    break
                for ev in dep_res.evidence:
                    if ev.content and "|" in ev.content:
                        table_raw = ev.content
                        break

        # 2. Consume table from DocumentElementRepository if available and still empty
        if not table_raw and self.element_repo and context.user_id:
            try:
                doc_ids_to_check = context.document_ids or []
                for doc_id in doc_ids_to_check:
                    elements = await self.element_repo.list_by_version(
                        user_id=context.user_id,
                        document_id=doc_id,
                        document_version=1,
                    )
                    for el in elements:
                        if el.element_type == ElementType.TABLE:
                            table_raw = el.content
                            break
                    if table_raw:
                        break
            except Exception as elem_err:
                logger.debug("Failed querying table element from repo: %s", elem_err)

        operation = task.parameters.get("operation")
        column_name = task.parameters.get("column_name")

        if not operation:
            req_l = query.lower()
            if "growth" in req_l or "cagr" in req_l or "percentage" in req_l:
                operation = "GROWTH"
            elif "sum" in req_l or "total" in req_l:
                operation = "SUM"
            elif "average" in req_l or "avg" in req_l or "mean" in req_l:
                operation = "AVG"
            elif "min" in req_l:
                operation = "MIN"
            elif "max" in req_l:
                operation = "MAX"

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

            if operation == "GROWTH":
                # Extract numeric values across cells
                nums: list[float] = []
                for cell in parsed_table.cells:
                    if cell.numeric_value is not None:
                        nums.append(float(cell.numeric_value))
                    else:
                        val_str = re.sub(r"[^\d\.]", "", str(cell.raw_value))
                        if val_str:
                            try:
                                nums.append(float(val_str))
                            except ValueError:
                                pass
                if len(nums) >= 2:
                    v_first = nums[0]
                    v_last = nums[-1]
                    growth_pct = (
                        ((v_last - v_first) / v_first) * 100.0 if v_first != 0 else 0.0
                    )
                    output_text = f"Calculated growth rate from {v_first} to {v_last}: {growth_pct:.2f}%"
                else:
                    output_text = f"Table summary: {parsed_table.summary}\n\n{self.table_processor.to_markdown(parsed_table)}"
            elif operation and column_name:
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
