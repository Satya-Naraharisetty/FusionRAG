import ast
import operator
from typing import Any

from app.chat.domain.agents import (
    ToolCategory,
    ToolDefinition,
    ToolPermission,
    ToolResult,
    ToolContext,
)
from app.chat.services.tools.base import BuiltinTool


class SafeCalculator:
    _operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: lambda x: x,
    }

    def evaluate(self, expression: str) -> float:
        expression = expression.strip()
        if not expression:
            raise ValueError("Expression is empty")

        try:
            node = ast.parse(expression, mode="eval")
            return self._eval_node(node.body)
        except Exception as e:
            raise ValueError(f"Invalid math syntax: {e}")

    def _eval_node(self, node):
        if hasattr(ast, "Num") and isinstance(node, ast.Num):  # Python < 3.8
            return node.n
        elif isinstance(node, ast.Constant):  # Python >= 3.8
            if isinstance(node.value, (int, float)):
                return node.value
            raise TypeError(f"Constant must be numeric, got {type(node.value)}")
        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op_type = type(node.op)
            if op_type in self._operators:
                if op_type == ast.Pow:
                    if right > 1000:
                        raise ValueError("Exponent too large. Max power is 1000.")
                return self._operators[op_type](left, right)
            raise TypeError(f"Unsupported binary operator: {op_type.__name__}")
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op_type = type(node.op)
            if op_type in self._operators:
                return self._operators[op_type](operand)
            raise TypeError(f"Unsupported unary operator: {op_type.__name__}")
        else:
            raise TypeError(f"Unsupported syntax: {type(node).__name__}")


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
