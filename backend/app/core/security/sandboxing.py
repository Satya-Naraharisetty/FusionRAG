import ast
import operator
from typing import Any


class SafeCalculator:
    # Map AST operators to standard python operator functions
    _OPERATORS: dict[type[Any], Any] = {
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

    _MAX_RESULT_MAGNITUDE = 1e15
    _MAX_RECURSION_DEPTH = 20

    @classmethod
    def evaluate(cls, expression: str) -> int | float:
        """
        Safely parse and evaluate a mathematical expression using python AST.
        Only numeric constants and basic mathematical operations are allowed.
        """
        if not expression or not expression.strip():
            raise ValueError("Empty expression.")

        try:
            # Parse in evaluation mode
            tree = ast.parse(expression.strip(), mode="eval")
            return cls._eval_node(tree.body, _depth=0)
        except Exception as e:
            raise ValueError(f"Invalid math syntax: {e}")

    @classmethod
    def _eval_node(cls, node: ast.AST, _depth: int = 0) -> int | float:
        if _depth > cls._MAX_RECURSION_DEPTH:
            raise ValueError("Expression too deeply nested.")

        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise TypeError("Only numeric constants are supported.")
        elif isinstance(node, ast.BinOp):
            left = cls._eval_node(node.left, _depth + 1)
            right = cls._eval_node(node.right, _depth + 1)
            op_type: type[Any] = type(node.op)
            if op_type in cls._OPERATORS:
                # Prevent unsafe operations
                if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                    raise ZeroDivisionError("Division by zero.")
                if op_type == ast.Pow:
                    if abs(left) > 10000 or right > 15 or right < -15:
                        raise ValueError(
                            "Exponent too large: Exponentiation base or power exceeds safety limits."
                        )
                result = cls._OPERATORS[op_type](left, right)
                if (
                    isinstance(result, (int, float))
                    and abs(result) > cls._MAX_RESULT_MAGNITUDE
                ):
                    raise ValueError("Result magnitude exceeds safety limits.")
                return result
            raise TypeError(f"Unsupported mathematical operator: {op_type.__name__}")
        elif isinstance(node, ast.UnaryOp):
            operand = cls._eval_node(node.operand, _depth + 1)
            op_type = type(node.op)
            if op_type in cls._OPERATORS:
                result = cls._OPERATORS[op_type](operand)
                if (
                    isinstance(result, (int, float))
                    and abs(result) > cls._MAX_RESULT_MAGNITUDE
                ):
                    raise ValueError("Result magnitude exceeds safety limits.")
                return result
            raise TypeError(f"Unsupported unary operator: {op_type.__name__}")
        else:
            raise TypeError(
                f"Node execution blocked for safety reasons: {type(node).__name__}"
            )
