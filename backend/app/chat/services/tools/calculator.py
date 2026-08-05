from typing import Any

from app.chat.domain.agents import (
    ToolCategory,
    ToolContext,
    ToolDefinition,
    ToolPermission,
    ToolResult,
)
from app.chat.services.tools.base import BuiltinTool
from app.core.security.sandboxing import SafeCalculator


class CalculatorTool(BuiltinTool):
    def __init__(self) -> None:
        self.calculator = SafeCalculator()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="calculator",
            description=(
                "Perform basic mathematical calculations safely. Supports basic "
                "arithmetic operators (+, -, *, /, **, //, %) and brackets."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate (e.g. '15 * 24 + 19').",
                    }
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
        expression = arguments["expression"]
        try:
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
