import pytest

from app.core.math.engine import SymbolicMathSubsystem


def test_symbolic_evaluate_expression():
    res = SymbolicMathSubsystem.evaluate_expression("2 * 3 + 4 * 5")
    assert res["numeric"] == 26.0
    assert "26" in res["exact"]
    assert "formatted_markdown" in res


def test_solve_algebraic_equation():
    res = SymbolicMathSubsystem.solve_equation("2*x + 10 = 30", variable="x")
    assert "10" in res["solutions"]
    assert "$x$" in res["formatted_markdown"]


def test_solve_quadratic_equation():
    res = SymbolicMathSubsystem.solve_equation("x**2 - 5*x + 6 = 0", variable="x")
    assert "2" in res["solutions"] and "3" in res["solutions"]


def test_solve_system_of_equations():
    res = SymbolicMathSubsystem.solve_system(
        equations=["x + y = 10", "2*x - y = 5"], variables=["x", "y"]
    )
    assert len(res["solutions"]) == 1
    sol = res["solutions"][0]
    assert sol["x"] == "5"
    assert sol["y"] == "5"


def test_calculus_derivative():
    res = SymbolicMathSubsystem.differentiate(
        "x**3 + 2*x**2 - 5*x + 7", variable="x", order=1
    )
    assert "3*x**2 + 4*x - 5" in res["result"]


def test_calculus_definite_and_indefinite_integral():
    # Indefinite
    res_indef = SymbolicMathSubsystem.integrate("x**2", variable="x")
    assert "x**3/3" in res_indef["result"]

    # Definite
    res_def = SymbolicMathSubsystem.integrate("x**2", variable="x", lower=0, upper=3)
    assert res_def["numeric"] == 9.0


def test_calculus_limit():
    res = SymbolicMathSubsystem.limit("sin(x)/x", variable="x", target=0)
    assert res["result"] == "1"


def test_taylor_series_expansion():
    res = SymbolicMathSubsystem.series_expansion(
        "exp(x)", variable="x", point=0, order=4
    )
    assert "1 + x + x**2/2 + x**3/6" in res["result"]


def test_engineering_ode_harmonic_oscillator():
    # y'' + 9y = 0
    res = SymbolicMathSubsystem.solve_ode(
        "Derivative(y(x), x, 2) + 9*y(x)", function_name="y", variable="x"
    )
    assert "sin(3*x)" in res["solution"] and "cos(3*x)" in res["solution"]


def test_engineering_laplace_and_inverse_laplace():
    # Laplace transform of exp(-2*t)
    res_lap = SymbolicMathSubsystem.laplace_transform("exp(-2*t)", t_var="t", s_var="s")
    assert "1/(s + 2)" in res_lap["laplace_transform"]

    # Inverse Laplace transform of 1/(s + 2)
    res_inv = SymbolicMathSubsystem.inverse_laplace_transform(
        "1/(s + 2)", s_var="s", t_var="t"
    )
    assert "exp(-2*t)" in res_inv["inverse_laplace_transform"]


def test_matrix_operations():
    # Determinant of 2x2
    mat = [[1, 2], [3, 4]]
    res_det = SymbolicMathSubsystem.matrix_operations("det", mat)
    assert res_det["numeric"] == -2.0

    # Inverse of 2x2
    res_inv = SymbolicMathSubsystem.matrix_operations("inv", mat)
    assert "-2" in res_inv["result"] and "1" in res_inv["result"]

    # Eigenvalues of diagonal matrix
    diag_mat = [[3, 0], [0, 5]]
    res_eig = SymbolicMathSubsystem.matrix_operations("eigenvalues", diag_mat)
    assert "3" in res_eig["eigenvalues"] and "5" in res_eig["eigenvalues"]


def test_physics_unit_conversions():
    # 10 kW to Watts
    res_kw = SymbolicMathSubsystem.convert_units(10, "kW", "W")
    assert res_kw["result"] == 10000.0

    # 1 atmosphere to Pascals
    res_atm = SymbolicMathSubsystem.convert_units(1, "atm", "Pa")
    assert pytest.approx(res_atm["result"], rel=1e-3) == 101325.0
