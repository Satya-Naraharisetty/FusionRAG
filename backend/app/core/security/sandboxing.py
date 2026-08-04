import ast
import operator
from typing import Any


class SafeCalculator:
    # Map AST operators to standard python operator functions
    _OPERATORS: dict[type[ast.operator], Any] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: lambda x: x,
    }

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
            return cls._eval_node(tree.body)
        except Exception as e:
            raise ValueError(f"Invalid or unsafe mathematical expression: {e}")

    @classmethod
    def _eval_node(cls, node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise TypeError("Only numeric constants are supported.")
        elif isinstance(node, ast.BinOp):
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            op_type = type(node.op)
            if op_type in cls._OPERATORS:
                # Prevent unsafe operations
                if op_type == ast.Div and right == 0:
                    raise ZeroDivisionError("Division by zero.")
                if op_type == ast.Pow:
                    if abs(left) > 10000 or right > 15 or right < -15:
                        raise ValueError("Exponentiation base or power exceeds safety limits.")
                return cls._OPERATORS[op_type](left, right)
            raise TypeError(f"Unsupported mathematical operator: {op_type.__name__}")
        elif isinstance(node, ast.UnaryOp):
            operand = cls._eval_node(node.operand)
            op_type = type(node.op)
            if op_type in cls._OPERATORS:
                return cls._OPERATORS[op_type](operand)
            raise TypeError(f"Unsupported unary operator: {op_type.__name__}")
        else:
            raise TypeError(f"Node execution blocked for safety reasons: {type(node).__name__}")
