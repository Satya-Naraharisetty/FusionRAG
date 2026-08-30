import pytest
from app.core.math.sandbox import (
    MathSecurityError,
    MathTimeoutError,
    run_with_math_timeout,
    validate_math_expression_ast,
)


def test_sandbox_blocks_import_and_eval():
    with pytest.raises(MathSecurityError):
        validate_math_expression_ast("__import__('os').system('ls')")

    with pytest.raises(MathSecurityError):
        validate_math_expression_ast("eval('1+1')")

    with pytest.raises(MathSecurityError):
        validate_math_expression_ast("open('/etc/passwd').read()")


def test_sandbox_blocks_dunder_attributes():
    with pytest.raises(MathSecurityError):
        validate_math_expression_ast("(1).__class__.__bases__")


def test_sandbox_allows_valid_math_syntax():
    validate_math_expression_ast("sin(x) + cos(y) * exp(2*t)")
    validate_math_expression_ast("diff(x**2 + 5*x, x)")
    validate_math_expression_ast("integrate(log(x), (x, 1, 10))")


@pytest.mark.asyncio
async def test_sandbox_timeout_guard():
    import time

    def slow_function():
        time.sleep(0.5)
        return "done"

    # Fast timeout should trigger MathTimeoutError
    with pytest.raises(MathTimeoutError):
        await run_with_math_timeout(slow_function, timeout_seconds=0.05)
