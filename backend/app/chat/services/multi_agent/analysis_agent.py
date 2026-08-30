import logging
import re
import time
from typing import Any

from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentFailureReason,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
)
from app.chat.services.multi_agent.base import BaseSpecialistAgent
from app.core.math.engine import MathEngine
from app.core.security.sandboxing import SafeCalculator

logger = logging.getLogger(__name__)


class AnalysisAgent(BaseSpecialistAgent):
    """
    Analysis and Mathematical specialist agent.
    Performs deterministic calculations, structured reasoning, comparisons,
    aggregations, and advanced scientific, engineering, financial, and symbolic
    evaluations via MathEngine and SafeCalculator.
    Does NOT have access to database, filesystem, network, or arbitrary tools.
    """

    def __init__(self) -> None:
        self.calculator = SafeCalculator()
        self.math_engine = MathEngine()

    @property
    def agent_type(self) -> AgentType:
        return AgentType.ANALYSIS

    def _parse_numeric_value(self, raw_str: str) -> float | None:
        """Parse a numeric string with optional currency symbols, commas, scale suffixes, and percentages."""
        if not raw_str or not isinstance(raw_str, str):
            return None
        cleaned = (
            raw_str.strip()
            .replace("$", "")
            .replace("€", "")
            .replace("£", "")
            .replace(",", "")
        )
        # Match number and optional scale suffix
        m = re.search(
            r"^([+-]?\d+(?:\.\d+)?)\s*(k|m|b|t|thousand|million|billion|trillion)?\s*%?$",
            cleaned,
            re.IGNORECASE,
        )
        if not m:
            return None
        base_num = float(m.group(1))
        scale = (m.group(2) or "").lower()
        if scale in ("k", "thousand"):
            base_num *= 1_000
        elif scale in ("m", "million"):
            base_num *= 1_000_000
        elif scale in ("b", "billion"):
            base_num *= 1_000_000_000
        elif scale in ("t", "trillion"):
            base_num *= 1_000_000_000_000
        return base_num

    def _extract_labeled_numbers(self, text: str) -> list[tuple[str, float]]:
        """
        Extract labeled numeric values (e.g. '2022: $10M', 'baseline: 100', 'revenue: 15.5 million')
        from text, avoiding arbitrary unlabeled numbers.
        """
        results: list[tuple[str, float]] = []
        if not text:
            return results

        # 1. Label-colon-value patterns e.g. "2022: $10M", "FY2023: 15.5m", "baseline = 100", "old: 50"
        label_pattern = re.compile(
            r"(?P<label>(?:FY\s*)?\b\d{4}\b|Q[1-4](?:\s*\d{4})?|\bold\b|\bnew\b|\bbaseline\b|\btarget\b|\brevenue\b|\bsales\b|\bincome\b|\bprofit\b|\bexpenses\b|\bcost\b|\btotal\b|\bval1\b|\bval2\b)"
            r"\s*[:=\-–—]\s*"
            r"[\$€£]?\s*(?P<val>[+-]?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:k|m|b|t|thousand|million|billion|trillion)?%?)",
            re.IGNORECASE,
        )
        for m in label_pattern.finditer(text):
            label = m.group("label").strip()
            val_str = m.group("val").strip()
            num = self._parse_numeric_value(val_str)
            if num is not None:
                results.append((label, num))

        # 2. "from X to Y" or "growth from X to Y" patterns
        from_to_pattern = re.compile(
            r"\bfrom\s+[\$€£]?\s*(?P<from_val>[+-]?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:k|m|b|t|thousand|million|billion|trillion)?%?)"
            r"\s+to\s+[\$€£]?\s*(?P<to_val>[+-]?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:k|m|b|t|thousand|million|billion|trillion)?%?)",
            re.IGNORECASE,
        )
        for m in from_to_pattern.finditer(text):
            v_from = self._parse_numeric_value(m.group("from_val"))
            v_to = self._parse_numeric_value(m.group("to_val"))
            if v_from is not None and v_to is not None:
                # If both are 4-digit years (e.g. from 2022 to 2023), skip them as they are temporal query filters
                if (
                    1900 <= v_from <= 2100
                    and 1900 <= v_to <= 2100
                    and float(v_from).is_integer()
                    and float(v_to).is_integer()
                ):
                    continue
                results.append(("from", v_from))
                results.append(("to", v_to))

        # 3. Descriptive metric patterns e.g. "sales of 15.5 million", "revenue of $10M"
        desc_pattern = re.compile(
            r"(?P<label>\brevenue\b|\bsales\b|\bprofit\b|\bincome\b|\bexpenses\b)\s+(?:of|was|reached|is)\s+[\$€£]?\s*(?P<val>[+-]?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:k|m|b|t|thousand|million|billion|trillion)?%?)",
            re.IGNORECASE,
        )
        for m in desc_pattern.finditer(text):
            label = m.group("label").strip()
            val_str = m.group("val").strip()
            num = self._parse_numeric_value(val_str)
            if num is not None:
                results.append((label, num))

        return results

    def _resolve_pairwise_operands(
        self,
        params: dict[str, Any],
        context_text: str,
        slot_names: tuple[str, str],
        task_request: str,
    ) -> tuple[float, float]:
        """
        Resolves a pair of numeric operands (e.g. old/new or val1/val2).
        Explicit parameters take precedence. Otherwise, labeled context extraction is used.
        """
        slot1, slot2 = slot_names
        # 1. Check if both explicit parameters are provided
        if (
            slot1 in params
            and slot2 in params
            and params[slot1] is not None
            and params[slot2] is not None
        ):
            return float(params[slot1]), float(params[slot2])

        # 2. Extract labeled numbers from upstream context and request
        all_text = f"{context_text}\n{task_request}"
        labeled_numbers = self._extract_labeled_numbers(all_text)

        if not labeled_numbers:
            raise ValueError(
                f"Missing numeric values for calculation: neither explicit parameters ({slot1}, {slot2}) "
                f"nor labeled numeric evidence were found in upstream dependencies."
            )

        # Check for year-labeled values e.g. ('2022', 10_000_000.0), ('2023', 15_000_000.0)
        year_entries = [
            (int(lbl), num)
            for lbl, num in labeled_numbers
            if lbl.isdigit() and len(lbl) == 4 and 1900 <= int(lbl) <= 2100
        ]
        if len(year_entries) >= 2:
            # Sort chronologically
            year_entries.sort(key=lambda x: x[0])
            # Earliest year is old_value, latest year is new_value
            return year_entries[0][1], year_entries[-1][1]

        # Check for 'old' / 'new' or 'baseline' / 'target'
        old_vals = [
            num for lbl, num in labeled_numbers if lbl.lower() in ("old", "baseline")
        ]
        new_vals = [
            num for lbl, num in labeled_numbers if lbl.lower() in ("new", "target")
        ]
        if old_vals and new_vals:
            return old_vals[0], new_vals[0]

        # Check for direct 'from' / 'to' pairs
        from_vals = [num for lbl, num in labeled_numbers if lbl.lower() == "from"]
        to_vals = [num for lbl, num in labeled_numbers if lbl.lower() == "to"]
        if from_vals and to_vals:
            return from_vals[0], to_vals[0]

        # Check for quarter-labeled values e.g. ('Q1', 10.0), ('Q2', 15.0)
        quarter_entries = [
            (lbl.upper(), num)
            for lbl, num in labeled_numbers
            if re.match(r"^Q[1-4]", lbl, re.IGNORECASE)
        ]
        if len(quarter_entries) >= 2:
            quarter_entries.sort(key=lambda x: x[0])
            return quarter_entries[0][1], quarter_entries[-1][1]

        # Check if exactly 2 distinct labeled values exist
        unique_vals = list({num for _, num in labeled_numbers})
        if len(unique_vals) == 2:
            # First encountered is slot1, second is slot2
            return labeled_numbers[0][1], labeled_numbers[1][1]

        if len(unique_vals) > 2:
            raise ValueError(
                f"Ambiguous numeric evidence: found multiple conflicting values ({unique_vals}) "
                f"without definitive chronological or baseline/target labels."
            )

        raise ValueError(
            f"Insufficient numeric evidence: could not resolve both operands for '{slot1}' and '{slot2}'."
        )

    def _resolve_values_list(
        self, params: dict[str, Any], context_text: str, task_request: str
    ) -> list[float]:
        """Resolves a list of numeric values for aggregate operations like sum or average."""
        if (
            "values" in params
            and isinstance(params["values"], list)
            and params["values"]
        ):
            return [float(v) for v in params["values"]]

        all_text = f"{context_text}\n{task_request}"
        labeled_numbers = self._extract_labeled_numbers(all_text)
        if labeled_numbers:
            return [num for _, num in labeled_numbers]

        raise ValueError(
            "Values list is missing and no labeled numeric evidence was found in upstream dependencies."
        )

    def _extract_expression(self, text: str) -> str | None:
        """Extract basic or symbolic arithmetic expressions from natural language text if present."""
        # 1. Check for explicit symbolic math expressions (e.g. diff(...), integrate(...), solve(...), sin(...))
        sym_match = re.search(
            r"\b(?:diff|integrate|limit|series|solve|dsolve|laplace_transform|inverse_laplace_transform|sin|cos|tan|exp|log|sqrt)\s*\([^)]+\)",
            text,
            re.IGNORECASE,
        )
        if sym_match:
            return sym_match.group(0).strip()

        # 2. Check for equations with variables (e.g. 2*x + 5 = 15 or y'' + 4*y = 0)
        eq_match = re.search(
            r"[a-zA-Z0-9_\^\*\+\-\/\(\)\s\.\=]+=[a-zA-Z0-9_\^\*\+\-\/\(\)\s\.]+", text
        )
        if eq_match and any(c in eq_match.group(0) for c in "+-*/^="):
            cand = eq_match.group(0).strip()
            if any(c.isdigit() or c.isalpha() for c in cand):
                return cand

        # 3. Standard numeric arithmetic
        match = re.search(r"[\d\.\s\+\-\*\/\(\)\%\^]+", text)
        if match:
            candidate = match.group(0).strip()
            if any(c.isdigit() for c in candidate) and any(
                c in "+-*/%^" for c in candidate
            ):
                return candidate
        return None

    async def execute_task(
        self,
        task: AgentTask,
        context: AgentExecutionContext,
    ) -> AgentResult:
        start_time = time.perf_counter()
        params = dict(task.parameters)
        expression = params.get("expression")
        operation = params.get("operation")

        try:
            # 1. Gather upstream dependency results
            dep_evidence_text = []
            for _dep_id, dep_res in context.dependency_results.items():
                if dep_res.success:
                    if dep_res.output:
                        dep_evidence_text.append(dep_res.output)
                    for ev in dep_res.evidence:
                        dep_evidence_text.append(ev.content)

            combined_context = "\n".join(dep_evidence_text)

            # 2. Check for domain operations handled by MathEngine
            domain_operations = {
                "solve",
                "solve_equation",
                "equation",
                "solve_system",
                "system_of_equations",
                "diff",
                "derivative",
                "differentiate",
                "integrate",
                "integral",
                "limit",
                "lim",
                "series",
                "taylor_series",
                "ode",
                "solve_ode",
                "differential_equation",
                "laplace",
                "laplace_transform",
                "inv_laplace",
                "inverse_laplace",
                "inverse_laplace_transform",
                "matrix",
                "matrix_operation",
                "matrix_operations",
                "unit_convert",
                "convert_units",
                "units",
                "cagr",
                "npv",
                "net_present_value",
                "irr",
                "internal_rate_of_return",
                "amortization",
                "loan",
                "pmt",
                "wacc",
                "cost_of_capital",
                "stats",
                "descriptive_stats",
                "statistics",
                "ttest",
                "hypothesis_test",
                "correlation",
                "corr",
                "curve_fit",
                "regression",
            }

            if operation and operation.lower() in domain_operations:
                math_res = self.math_engine.execute_operation(operation, params)
                output_str = math_res.get(
                    "formatted_markdown", str(math_res.get("result", math_res))
                )
                structured = math_res

            elif operation == "growth_rate":
                old_val, new_val = self._resolve_pairwise_operands(
                    params, combined_context, ("old_value", "new_value"), task.request
                )
                if old_val == 0:
                    raise ZeroDivisionError(
                        "Cannot compute growth rate from baseline of zero."
                    )
                rate = ((new_val - old_val) / abs(old_val)) * 100
                result_val = round(rate, 4)
                output_str = (
                    f"Growth rate from {old_val} to {new_val}: {result_val:.2f}%\n\n"
                    f"$$\\text{{Growth Rate}} = \\frac{{{new_val:g} - {old_val:g}}}{{|{old_val:g}|}} \\times 100\\% = {result_val:.2f}\\%$$"
                )
                structured = {
                    "operation": "growth_rate",
                    "old_value": old_val,
                    "new_value": new_val,
                    "growth_rate_pct": result_val,
                }

            elif operation == "percentage_change":
                base_val, target_val = self._resolve_pairwise_operands(
                    params,
                    combined_context,
                    ("base_value", "target_value"),
                    task.request,
                )
                if base_val == 0:
                    raise ZeroDivisionError(
                        "Cannot compute percentage change from base of zero."
                    )
                pct = ((target_val - base_val) / base_val) * 100
                result_val = round(pct, 4)
                output_str = (
                    f"Percentage change from {base_val} to {target_val}: {result_val:.2f}%\n\n"
                    f"$$\\Delta\\% = \\frac{{{target_val:g} - {base_val:g}}}{{{base_val:g}}} \\times 100\\% = {result_val:.2f}\\%$$"
                )
                structured = {
                    "operation": "percentage_change",
                    "base_value": base_val,
                    "target_value": target_val,
                    "percentage": result_val,
                }

            elif operation == "sum":
                values = self._resolve_values_list(
                    params, combined_context, task.request
                )
                total = sum(values)
                output_str = f"Sum of {values}: {total}\n\n$$\\sum x_i = {total:g}$$"
                structured = {"operation": "sum", "values": values, "total": total}

            elif operation == "average":
                values = self._resolve_values_list(
                    params, combined_context, task.request
                )
                if not values:
                    raise ValueError(
                        "Values list cannot be empty for average calculation."
                    )
                avg = sum(values) / len(values)
                output_str = (
                    f"Average of {values}: {avg:.4f}\n\n$$\\bar{{x}} = {avg:.4f}$$"
                )
                structured = {"operation": "average", "values": values, "average": avg}

            elif operation == "difference":
                val1, val2 = self._resolve_pairwise_operands(
                    params, combined_context, ("val1", "val2"), task.request
                )
                diff = val1 - val2
                output_str = f"Difference between {val1} and {val2}: {diff}\n\n$${val1:g} - {val2:g} = {diff:g}$$"
                structured = {
                    "operation": "difference",
                    "val1": val1,
                    "val2": val2,
                    "difference": diff,
                }

            elif expression:
                try:
                    math_res = self.math_engine.calculate(expression)
                    output_str = math_res.get(
                        "formatted_markdown",
                        str(math_res.get("exact", math_res.get("numeric"))),
                    )
                    structured = math_res
                except Exception:
                    val = self.calculator.evaluate(expression)
                    output_str = (
                        f"Calculation result: {val}\n\n$${expression} = {val}$$"
                    )
                    structured = {"expression": expression, "result": val}

            else:
                # Attempt to extract expression from task request
                extracted = self._extract_expression(task.request)
                if extracted:
                    try:
                        math_res = self.math_engine.calculate(extracted)
                        output_str = math_res.get(
                            "formatted_markdown",
                            str(math_res.get("exact", math_res.get("numeric"))),
                        )
                        structured = math_res
                    except Exception:
                        val = self.calculator.evaluate(extracted)
                        output_str = f"Calculation result for '{extracted}': {val}\n\n$${extracted} = {val}$$"
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
            logger.warning(
                "AnalysisAgent execution failed for task %s: %s", task.task_id, e
            )
            failure_reason = (
                AgentFailureReason.VALIDATION_ERROR
                if "Missing" in str(e)
                or "Ambiguous" in str(e)
                or "Insufficient" in str(e)
                else AgentFailureReason.EXECUTION_ERROR
            )
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                status=AgentTaskStatus.FAILED,
                success=False,
                output="",
                error=f"Analysis calculation error: {e}",
                failure_reason=failure_reason,
                execution_time_ms=elapsed_ms,
            )
