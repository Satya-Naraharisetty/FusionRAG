import ast
import asyncio
import concurrent.futures
from collections.abc import Callable
from typing import Any

# Blacklisted identifiers and attributes that must never be evaluated
BLOCKED_IDENTIFIERS: frozenset[str] = frozenset(
    {
        "__import__",
        "__builtins__",
        "__class__",
        "__subclasses__",
        "__bases__",
        "__mro__",
        "__globals__",
        "__code__",
        "__closure__",
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "print",
        "exit",
        "quit",
        "help",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "globals",
        "locals",
        "vars",
        "os",
        "sys",
        "subprocess",
        "shutil",
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "posix",
        "nt",
        "pty",
        "platform",
    }
)

# Allowed AST node types for mathematical parsing
ALLOWED_AST_NODES: frozenset[type[ast.AST]] = frozenset(
    {
        ast.Expression,
        ast.Expr,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Name,
        ast.Call,
        ast.keyword,
        ast.List,
        ast.Tuple,
        ast.Dict,
        ast.Compare,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Load,
        ast.Subscript,
        ast.Slice,
    }
)


class MathSecurityError(ValueError):
    """Raised when an expression contains unauthorized AST nodes, functions, or identifiers."""

    pass


class MathTimeoutError(TimeoutError):
    """Raised when a mathematical computation exceeds the allowed execution time."""

    pass


class ASTSecurityValidator(ast.NodeVisitor):
    """
    Validates that an AST tree only contains allowed mathematical operators,
    constants, and whitelisted identifiers, blocking all dangerous introspections.
    """

    def visit(self, node: ast.AST) -> Any:
        node_type = type(node)
        if node_type not in ALLOWED_AST_NODES:
            raise MathSecurityError(
                f"Unauthorized syntax blocked for security: {node_type.__name__}"
            )
        return super().visit(node)

    def visit_Name(self, node: ast.Name) -> Any:
        name = node.id
        if name.startswith("_") or name.lower() in BLOCKED_IDENTIFIERS:
            raise MathSecurityError(f"Unauthorized identifier blocked: '{name}'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        attr = node.attr
        if attr.startswith("_") or attr.lower() in BLOCKED_IDENTIFIERS:
            raise MathSecurityError(f"Unauthorized attribute access blocked: '{attr}'")
        self.generic_visit(node)


def validate_math_expression_ast(expr_str: str) -> None:
    """
    Parses and checks a mathematical expression against strict AST security policies.
    """
    if not expr_str or not expr_str.strip():
        raise MathSecurityError("Empty mathematical expression.")

    try:
        tree = ast.parse(expr_str.strip(), mode="eval")
    except SyntaxError as e:
        raise MathSecurityError(f"Invalid math syntax: {e}") from e

    validator = ASTSecurityValidator()
    validator.visit(tree)


async def run_with_math_timeout(
    func: Callable[..., Any],
    *args: Any,
    timeout_seconds: float = 3.0,
    **kwargs: Any,
) -> Any:
    """
    Executes a CPU-bound math function in a thread pool with a strict timeout guard.
    """
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = loop.run_in_executor(pool, lambda: func(*args, **kwargs))
        try:
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except TimeoutError as err:
            raise MathTimeoutError(
                f"Computation timed out after {timeout_seconds} seconds."
            ) from err
