import logging
import re
import time

from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentFailureReason,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
)
from app.chat.services.multi_agent.base import BaseSpecialistAgent
from app.core.security.sandboxing import SafeCalculator

logger = logging.getLogger(__name__)


class AnalysisAgent(BaseSpecialistAgent):
    """
    Analysis specialist agent.
    Performs deterministic calculations, structured reasoning, comparisons,
    aggregations, and numerical transformations using SafeCalculator.
    Does NOT have access to database, filesystem, network, or arbitrary tools.
    """

    def __init__(self) -> None:
        self.calculator = SafeCalculator()

    @property
    def agent_type(self) -> AgentType:
        return AgentType.ANALYSIS

    def _extract_expression(self, text: str) -> str | None:
        """Extract basic arithmetic expressions from natural language text if present."""
        # Match common math patterns e.g. "15 * 2 + 10" or "(100 - 80) / 80"
        match = re.search(r"[\d\.\s\+\-\*\/\(\)\%]+", text)
        if match:
            candidate = match.group(0).strip()
            # Verify candidate has at least one digit and one operator
            if any(c.isdigit() for c in candidate) and any(
                c in "+-*/%" for c in candidate
            ):
                return candidate
        return None

    async def execute_task(
        self,
        task: AgentTask,
        context: AgentExecutionContext,
    ) -> AgentResult:
        start_time = time.perf_counter()
        params = task.parameters
        expression = params.get("expression")
        operation = params.get("operation")

        try:
            # 1. Check if upstream dependency results provide input data
            dep_evidence_text = []
            for _dep_id, dep_res in context.dependency_results.items():
                if dep_res.success:
                    if dep_res.output:
                        dep_evidence_text.append(dep_res.output)
                    for ev in dep_res.evidence:
                        dep_evidence_text.append(ev.content)

            combined_context = "\n".join(dep_evidence_text)

            # 2. Structured Operation dispatch
            if operation == "growth_rate":
                old_val = float(params["old_value"])
                new_val = float(params["new_value"])
                if old_val == 0:
                    raise ZeroDivisionError(
                        "Cannot compute growth rate from baseline of zero."
                    )
                rate = ((new_val - old_val) / abs(old_val)) * 100
                result_val = round(rate, 4)
                output_str = (
                    f"Growth rate from {old_val} to {new_val}: {result_val:.2f}%"
                )
                structured = {
                    "operation": "growth_rate",
                    "old_value": old_val,
                    "new_value": new_val,
                    "growth_rate_pct": result_val,
                }

            elif operation == "percentage_change":
                base_val = float(params["base_value"])
                target_val = float(params["target_value"])
                if base_val == 0:
                    raise ZeroDivisionError(
                        "Cannot compute percentage change from base of zero."
                    )
                pct = ((target_val - base_val) / base_val) * 100
                result_val = round(pct, 4)
                output_str = f"Percentage change: {result_val:.2f}%"
                structured = {
                    "operation": "percentage_change",
                    "percentage": result_val,
                }

            elif operation == "sum":
                values = [float(v) for v in params.get("values", [])]
                total = sum(values)
                output_str = f"Sum of {values}: {total}"
                structured = {"operation": "sum", "values": values, "total": total}

            elif operation == "average":
                values = [float(v) for v in params.get("values", [])]
                if not values:
                    raise ValueError(
                        "Values list cannot be empty for average calculation."
                    )
                avg = sum(values) / len(values)
                output_str = f"Average of {values}: {avg:.4f}"
                structured = {"operation": "average", "values": values, "average": avg}

            elif operation == "difference":
                val1 = float(params["val1"])
                val2 = float(params["val2"])
                diff = val1 - val2
                output_str = f"Difference between {val1} and {val2}: {diff}"
                structured = {
                    "operation": "difference",
                    "val1": val1,
                    "val2": val2,
                    "difference": diff,
                }

            elif expression:
                val = self.calculator.evaluate(expression)
                output_str = f"Calculation result: {val}"
                structured = {"expression": expression, "result": val}

            else:
                # Attempt to extract expression from task request
                extracted = self._extract_expression(task.request)
                if extracted:
                    val = self.calculator.evaluate(extracted)
                    output_str = f"Calculation result for '{extracted}': {val}"
                    structured = {"expression": extracted, "result": val}
                else:
                    output_str = f"Analysis completed on available context ({len(combined_context)} characters examined)."
                    structured = {"context_length": len(combined_context)}

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.COMPLETED,
                success=True,
                output=output_str,
                evidence=[],
                citations=[],
                metadata=structured,
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("AnalysisAgent execution failed for task %s", task.task_id)
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error=f"Analysis calculation error: {e}",
                failure_reason=AgentFailureReason.EXECUTION_ERROR,
                execution_time_ms=elapsed_ms,
            )
