from typing import Any

from app.chat.domain.agents import (
    ToolCategory,
    ToolContext,
    ToolDefinition,
    ToolPermission,
    ToolResult,
)
from app.chat.services.tools.base import BuiltinTool
from app.core.math.engine import MathEngine
from app.core.security.sandboxing import SafeCalculator


class CalculatorTool(BuiltinTool):
    def __init__(self) -> None:
        self.calculator = SafeCalculator()
        self.math_engine = MathEngine()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="calculator",
            description=(
                "Perform scientific, engineering, financial, and symbolic mathematical calculations safely. "
                "Supports arithmetic (+, -, *, /, **, //, %), calculus (diff, integrate, limit, series), "
                "trigonometry (sin, cos, tan), algebra (solve), ODEs (dsolve), and unit conversions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression or formula to evaluate (e.g. '15 * 24 + 19', 'diff(sin(x)*exp(x), x)', 'integrate(x**2, x)').",
                    },
                    "operation": {
                        "type": "string",
                        "description": "Optional specific operation (e.g. 'solve_equation', 'ode', 'cagr', 'npv', 'unit_convert', 'stats').",
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Optional structured parameters for domain calculations (e.g. for ODEs, financial models, or unit conversions).",
                    },
                },
                "required": ["expression"],
            },
        )

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.UTILITY

    @property
    def required_permission(self) -> ToolPermission:
        return ToolPermission.READ

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
        cancellation_token: Any | None = None,
    ) -> ToolResult:
        expression = arguments.get("expression", "")
        operation = arguments.get("operation")
        params = arguments.get("parameters") or {}

        try:
            if operation:
                if "expression" not in params and expression:
                    params["expression"] = expression
                res = self.math_engine.execute_operation(operation, params)
                content = res.get("formatted_markdown", str(res.get("result", res)))
                return ToolResult(
                    tool_call_id="",
                    name=self.definition.name,
                    content=content,
                    structured_output=res,
                    is_error=False,
                )

            # Try MathEngine first for rich symbolic & numerical math
            try:
                res = self.math_engine.calculate(expression)
                content = res.get(
                    "formatted_markdown", str(res.get("exact", res.get("numeric")))
                )
                return ToolResult(
                    tool_call_id="",
                    name=self.definition.name,
                    content=content,
                    structured_output=res,
                    is_error=False,
                )
            except Exception:
                # Fall back to legacy basic SafeCalculator
                val = self.calculator.evaluate(expression)
                return ToolResult(
                    tool_call_id="",
                    name=self.definition.name,
                    content=str(val),
                    structured_output={"result": val},
                    is_error=False,
                )

        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name=self.definition.name,
                content=f"Calculation Error: {e}",
                is_error=True,
            )
