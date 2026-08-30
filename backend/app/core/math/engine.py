import logging
from typing import Any

from app.core.math.sandbox import (
    validate_math_expression_ast,
)

logger = logging.getLogger(__name__)


class LaTeXStepFormatter:
    """Formats mathematical expressions and solutions into KaTeX-compatible LaTeX markup."""

    @staticmethod
    def format_solution(
        title: str,
        problem_latex: str,
        steps: list[str],
        result_latex: str,
        notes: str | None = None,
    ) -> str:
        parts = [f"### {title}\n"]
        if problem_latex:
            parts.append(f"$$\n{problem_latex}\n$$\n")
        if steps:
            parts.append("**Step-by-step derivation:**")
            for i, step in enumerate(steps, 1):
                parts.append(f"{i}. {step}")
            parts.append("")
        if result_latex:
            parts.append(f"**Final Result:**\n$$\n{result_latex}\n$$")
        if notes:
            parts.append(f"\n> **Note:** {notes}")
        return "\n".join(parts)


class SymbolicMathSubsystem:
    """
    Symbolic computation subsystem powered by SymPy.
    Covers algebra, single/multivariable calculus, ODEs, transforms,
    linear algebra, complex numbers/phasors, and physics units.
    """

    @staticmethod
    def _get_sympy() -> Any:
        import sympy

        return sympy

    @classmethod
    def evaluate_expression(cls, expr_str: str) -> dict[str, Any]:
        validate_math_expression_ast(expr_str)
        sp = cls._get_sympy()
        expr = sp.sympify(expr_str)
        exact_val = expr
        float_val = float(expr.evalf()) if expr.is_number else None
        latex_str = sp.latex(exact_val)

        return {
            "expression": expr_str,
            "exact": str(exact_val),
            "numeric": float_val,
            "latex": f"{sp.latex(sp.sympify(expr_str))} = {latex_str}",
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Mathematical Evaluation",
                problem_latex=sp.latex(sp.sympify(expr_str)),
                steps=[f"Evaluated exact symbolic expression to: `${latex_str}$`"],
                result_latex=f"{latex_str}"
                + (f" \\approx {float_val:.6g}" if float_val is not None else ""),
            ),
        }

    @classmethod
    def solve_equation(cls, equation_str: str, variable: str = "x") -> dict[str, Any]:
        sp = cls._get_sympy()
        var_sym = sp.Symbol(variable)

        # Parse equation (supports '=' or expression = 0)
        if "=" in equation_str:
            lhs_str, rhs_str = equation_str.split("=", 1)
            validate_math_expression_ast(lhs_str)
            validate_math_expression_ast(rhs_str)
            lhs = sp.sympify(lhs_str.strip())
            rhs = sp.sympify(rhs_str.strip())
            eq = sp.Eq(lhs, rhs)
        else:
            validate_math_expression_ast(equation_str)
            eq = sp.Eq(sp.sympify(equation_str.strip()), 0)

        solutions = sp.solve(eq, var_sym)
        sol_latex = (
            ", ".join(sp.latex(s) for s in solutions) if solutions else "\\emptyset"
        )
        eq_latex = sp.latex(eq)

        steps = [
            f"Set up equation: `${eq_latex}$`",
            f"Isolate and solve for variable `${variable}$` using algebraic elimination/root-finding.",
            f"Found solutions: `${sol_latex}$`",
        ]

        return {
            "equation": equation_str,
            "variable": variable,
            "solutions": [str(s) for s in solutions],
            "latex": f"{variable} \\in \\{{{sol_latex}\\}}",
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title=f"Algebraic Solution for ${variable}$",
                problem_latex=eq_latex,
                steps=steps,
                result_latex=f"{variable} = {sol_latex}",
            ),
        }

    @classmethod
    def solve_system(cls, equations: list[str], variables: list[str]) -> dict[str, Any]:
        sp = cls._get_sympy()
        sym_vars = [sp.Symbol(v) for v in variables]
        sp_eqs = []

        for eq_str in equations:
            if "=" in eq_str:
                lhs_str, rhs_str = eq_str.split("=", 1)
                validate_math_expression_ast(lhs_str)
                validate_math_expression_ast(rhs_str)
                sp_eqs.append(sp.Eq(sp.sympify(lhs_str), sp.sympify(rhs_str)))
            else:
                validate_math_expression_ast(eq_str)
                sp_eqs.append(sp.Eq(sp.sympify(eq_str), 0))

        sol_dict = sp.solve(sp_eqs, sym_vars, dict=True)
        eqs_latex = (
            "\\begin{cases} "
            + " \\\\ ".join(sp.latex(e) for e in sp_eqs)
            + " \\end{cases}"
        )

        result_lines = []
        if sol_dict and isinstance(sol_dict, list):
            for s in sol_dict:
                line = ", ".join(f"{sp.latex(k)} = {sp.latex(v)}" for k, v in s.items())
                result_lines.append(line)
        res_latex = (
            " \\quad \\text{or} \\quad ".join(result_lines)
            if result_lines
            else "\\text{No solution}"
        )

        steps = [
            "Formulated system of simultaneous equations.",
            "Applied Gaussian / symbolic elimination across variables.",
            f"Resolved variables: `${res_latex}$`",
        ]

        return {
            "equations": equations,
            "variables": variables,
            "solutions": [
                {str(k): str(v) for k, v in s.items()} for s in (sol_dict or [])
            ],
            "latex": res_latex,
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="System of Equations Solution",
                problem_latex=eqs_latex,
                steps=steps,
                result_latex=res_latex,
            ),
        }

    @classmethod
    def differentiate(
        cls, expression: str, variable: str = "x", order: int = 1
    ) -> dict[str, Any]:
        validate_math_expression_ast(expression)
        sp = cls._get_sympy()
        var_sym = sp.Symbol(variable)
        expr = sp.sympify(expression)
        derivative = sp.diff(expr, var_sym, order)

        d_symbol = (
            f"\\frac{{d^{order}}}{{d{variable}^{order}}}"
            if order > 1
            else f"\\frac{{d}}{{d{variable}}}"
        )
        prob_latex = f"{d_symbol} \\left( {sp.latex(expr)} \\right)"
        res_latex = sp.latex(derivative)

        steps = [
            f"Target function: $f({variable}) = {sp.latex(expr)}$",
            f"Applied calculus differentiation rules with respect to ${variable}$ (order {order}).",
            f"Derivative: `${res_latex}$`",
        ]

        return {
            "expression": expression,
            "variable": variable,
            "order": order,
            "result": str(derivative),
            "latex": f"{prob_latex} = {res_latex}",
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title=f"Derivative (Order {order})",
                problem_latex=prob_latex,
                steps=steps,
                result_latex=res_latex,
            ),
        }

    @classmethod
    def integrate(
        cls,
        expression: str,
        variable: str = "x",
        lower: float | str | None = None,
        upper: float | str | None = None,
    ) -> dict[str, Any]:
        validate_math_expression_ast(expression)
        sp = cls._get_sympy()
        var_sym = sp.Symbol(variable)
        expr = sp.sympify(expression)

        if lower is not None and upper is not None:
            low_sym = sp.sympify(lower)
            up_sym = sp.sympify(upper)
            integral = sp.integrate(expr, (var_sym, low_sym, up_sym))
            prob_latex = f"\\int_{{{sp.latex(low_sym)}}}^{{{sp.latex(up_sym)}}} {sp.latex(expr)} \\, d{variable}"
            res_latex = sp.latex(integral)
            steps = [
                f"Integrand: $f({variable}) = {sp.latex(expr)}$",
                f"Found antiderivative: $F({variable}) = {sp.latex(sp.integrate(expr, var_sym))}$",
                f"Evaluated definite integral boundaries from ${sp.latex(low_sym)}$ to ${sp.latex(up_sym)}$.",
            ]
        else:
            integral = sp.integrate(expr, var_sym)
            prob_latex = f"\\int {sp.latex(expr)} \\, d{variable}"
            res_latex = f"{sp.latex(integral)} + C"
            steps = [
                f"Integrand: $f({variable}) = {sp.latex(expr)}$",
                "Applied integration techniques (symbolic antiderivative calculation).",
                "Added integration constant $C$.",
            ]

        float_val = (
            float(integral.evalf())
            if hasattr(integral, "is_number") and integral.is_number
            else None
        )

        return {
            "expression": expression,
            "variable": variable,
            "lower": str(lower) if lower is not None else None,
            "upper": str(upper) if upper is not None else None,
            "result": str(integral),
            "numeric": float_val,
            "latex": f"{prob_latex} = {res_latex}",
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Integral Calculation",
                problem_latex=prob_latex,
                steps=steps,
                result_latex=res_latex
                + (f" \\approx {float_val:.6g}" if float_val is not None else ""),
            ),
        }

    @classmethod
    def limit(
        cls,
        expression: str,
        variable: str = "x",
        target: float | str = 0,
        direction: str = "+-",
    ) -> dict[str, Any]:
        validate_math_expression_ast(expression)
        sp = cls._get_sympy()
        var_sym = sp.Symbol(variable)
        target_sym = sp.sympify(target)
        expr = sp.sympify(expression)

        lim = sp.limit(expr, var_sym, target_sym, dir=direction)
        prob_latex = f"\\lim_{{{variable} \\to {sp.latex(target_sym)}}} \\left( {sp.latex(expr)} \\right)"
        res_latex = sp.latex(lim)

        return {
            "expression": expression,
            "variable": variable,
            "target": str(target),
            "result": str(lim),
            "latex": f"{prob_latex} = {res_latex}",
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Limit Evaluation",
                problem_latex=prob_latex,
                steps=[
                    f"Computed asymptotic expansion as ${variable} \\to {sp.latex(target_sym)}$."
                ],
                result_latex=res_latex,
            ),
        }

    @classmethod
    def series_expansion(
        cls,
        expression: str,
        variable: str = "x",
        point: float | str = 0,
        order: int = 6,
    ) -> dict[str, Any]:
        validate_math_expression_ast(expression)
        sp = cls._get_sympy()
        var_sym = sp.Symbol(variable)
        pt_sym = sp.sympify(point)
        expr = sp.sympify(expression)

        series = sp.series(expr, var_sym, pt_sym, n=order)
        prob_latex = f"\\text{{Taylor series of }} {sp.latex(expr)} \\text{{ around }} {variable} = {sp.latex(pt_sym)}"
        res_latex = sp.latex(series)

        return {
            "expression": expression,
            "variable": variable,
            "point": str(point),
            "order": order,
            "result": str(series),
            "latex": res_latex,
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title=f"Taylor Series Expansion (Order {order})",
                problem_latex=prob_latex,
                steps=[
                    f"Expanded around point ${variable} = {sp.latex(pt_sym)}$ up to $\\mathcal{{O}}({variable}^{{{order}}})$. "
                ],
                result_latex=res_latex,
            ),
        }

    @classmethod
    def solve_ode(
        cls,
        ode_expression: str,
        function_name: str = "y",
        variable: str = "x",
        initial_conditions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Solves 1st and 2nd order Ordinary Differential Equations (ODEs).
        e.g. "Derivative(y(x), x, 2) + 4*y(x) = 0"
        """
        validate_math_expression_ast(ode_expression)
        sp = cls._get_sympy()
        x = sp.Symbol(variable)
        y = sp.Function(function_name)(x)

        # Parse ODE
        parsed_ode = sp.sympify(
            ode_expression,
            locals={function_name: sp.Function(function_name), variable: x},
        )
        if isinstance(parsed_ode, sp.Equality):
            eq = parsed_ode
        else:
            eq = sp.Eq(parsed_ode, 0)

        ics = None
        if initial_conditions:
            ics = {}
            for k, v in initial_conditions.items():
                ics[
                    sp.sympify(
                        k,
                        locals={function_name: sp.Function(function_name), variable: x},
                    )
                ] = sp.sympify(v)

        sol = sp.dsolve(eq, y, ics=ics)
        prob_latex = sp.latex(eq)
        res_latex = sp.latex(sol)

        steps = [
            f"Classified differential equation: `${prob_latex}$`",
            "Determined characteristic equation / integrating factor / homogeneous & particular solutions.",
            f"Applied initial conditions: {ics}"
            if ics
            else "Retained arbitrary constants $C_1, C_2, \\dots$",
            f"General solution: `${res_latex}$`",
        ]

        return {
            "ode": ode_expression,
            "solution": str(sol),
            "latex": res_latex,
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Ordinary Differential Equation (ODE) Solution",
                problem_latex=prob_latex,
                steps=steps,
                result_latex=res_latex,
            ),
        }

    @classmethod
    def laplace_transform(
        cls, expression: str, t_var: str = "t", s_var: str = "s"
    ) -> dict[str, Any]:
        validate_math_expression_ast(expression)
        sp = cls._get_sympy()
        t = sp.Symbol(t_var, positive=True)
        s = sp.Symbol(s_var)
        expr = sp.sympify(expression, locals={t_var: t})

        res, _, _ = sp.laplace_transform(expr, t, s)
        prob_latex = f"\\mathcal{{L}}\\left\\{{ {sp.latex(expr)} \\right\\}}(s)"
        res_latex = sp.latex(res)

        return {
            "expression": expression,
            "laplace_transform": str(res),
            "latex": f"{prob_latex} = {res_latex}",
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Laplace Transform (Frequency Domain)",
                problem_latex=prob_latex,
                steps=[
                    f"Converted time-domain signal $f({t_var}) = {sp.latex(expr)}$ into $s$-domain via $\\int_0^\\infty e^{{-st}} f(t) dt$.",
                ],
                result_latex=f"F({s_var}) = {res_latex}",
            ),
        }

    @classmethod
    def inverse_laplace_transform(
        cls, expression: str, s_var: str = "s", t_var: str = "t"
    ) -> dict[str, Any]:
        validate_math_expression_ast(expression)
        sp = cls._get_sympy()
        s = sp.Symbol(s_var)
        t = sp.Symbol(t_var, positive=True)
        expr = sp.sympify(expression, locals={s_var: s})

        res = sp.inverse_laplace_transform(expr, s, t)
        prob_latex = f"\\mathcal{{L}}^{{-1}}\\left\\{{ {sp.latex(expr)} \\right\\}}(t)"
        res_latex = sp.latex(res)

        return {
            "expression": expression,
            "inverse_laplace_transform": str(res),
            "latex": f"{prob_latex} = {res_latex}",
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Inverse Laplace Transform (Time Domain)",
                problem_latex=prob_latex,
                steps=[
                    f"Applied partial fraction decomposition and inverse transform to recover $f({t_var})$.",
                ],
                result_latex=f"f({t_var}) = {res_latex}",
            ),
        }

    @classmethod
    def matrix_operations(
        cls,
        operation: str,
        matrix_a: list[list[Any]],
        matrix_b: list[list[Any]] | None = None,
    ) -> dict[str, Any]:
        sp = cls._get_sympy()
        mat_a = sp.Matrix(matrix_a)
        op_lower = operation.lower().strip()
        mat_latex = sp.latex(mat_a)

        if op_lower in ("det", "determinant"):
            det_val = mat_a.det()
            res_latex = sp.latex(det_val)
            return {
                "operation": "determinant",
                "result": str(det_val),
                "numeric": float(det_val)
                if hasattr(det_val, "is_number") and det_val.is_number
                else None,
                "latex": f"\\det({mat_latex}) = {res_latex}",
                "formatted_markdown": LaTeXStepFormatter.format_solution(
                    title="Matrix Determinant",
                    problem_latex=f"\\det {mat_latex}",
                    steps=["Evaluated cofactor expansion / determinant algorithm."],
                    result_latex=f"\\det(A) = {res_latex}",
                ),
            }

        elif op_lower in ("inv", "inverse"):
            inv_mat = mat_a.inv()
            res_latex = sp.latex(inv_mat)
            return {
                "operation": "inverse",
                "result": str(inv_mat),
                "latex": f"A^{{-1}} = {res_latex}",
                "formatted_markdown": LaTeXStepFormatter.format_solution(
                    title="Matrix Inverse",
                    problem_latex=f"A = {mat_latex}",
                    steps=[
                        "Checked non-zero determinant $\\det(A) \\neq 0$",
                        "Calculated adjugate matrix and inverted.",
                    ],
                    result_latex=f"A^{{-1}} = {res_latex}",
                ),
            }

        elif op_lower in ("eigen", "eigenvalues", "eigenvectors"):
            eigenvals = mat_a.eigenvals()
            eigenvects = mat_a.eigenvects()
            vals_latex = ", ".join(
                f"\\lambda = {sp.latex(k)} \\text{{ (mult: {v})}}"
                for k, v in eigenvals.items()
            )
            vects_str = [
                f"λ={sp.latex(v[0])}: {[sp.latex(vec) for vec in v[2]]}"
                for v in eigenvects
            ]

            return {
                "operation": "eigenvalues_and_eigenvectors",
                "eigenvalues": {str(k): v for k, v in eigenvals.items()},
                "eigenvectors": [str(v) for v in eigenvects],
                "latex": vals_latex,
                "formatted_markdown": LaTeXStepFormatter.format_solution(
                    title="Matrix Eigenvalues & Eigenvectors",
                    problem_latex=f"A = {mat_latex}",
                    steps=[
                        "Solved characteristic polynomial $\\det(A - \\lambda I) = 0$.",
                        f"Eigenvalues: ${vals_latex}$",
                        "Computed null space $(A - \\lambda I)\\mathbf{v} = 0$ for each eigenvector.",
                    ],
                    result_latex=vals_latex,
                    notes=f"Eigenspaces: {'; '.join(vects_str)}",
                ),
            }

        elif op_lower in ("mul", "multiply", "matmul") and matrix_b:
            mat_b = sp.Matrix(matrix_b)
            prod = mat_a * mat_b
            res_latex = sp.latex(prod)
            return {
                "operation": "multiplication",
                "result": str(prod),
                "latex": f"{mat_latex} \\times {sp.latex(mat_b)} = {res_latex}",
                "formatted_markdown": LaTeXStepFormatter.format_solution(
                    title="Matrix Multiplication",
                    problem_latex=f"{mat_latex} \\times {sp.latex(mat_b)}",
                    steps=[
                        "Computed inner dot products of row vectors and column vectors."
                    ],
                    result_latex=res_latex,
                ),
            }

        raise ValueError(f"Unsupported matrix operation: {operation}")

    @classmethod
    def convert_units(
        cls, quantity: float, from_unit_str: str, to_unit_str: str
    ) -> dict[str, Any]:
        """Converts engineering and physics units using SymPy's physics unit framework."""
        cls._get_sympy()
        from sympy.physics import units

        def _resolve_unit(u_name: str) -> Any:
            u_clean = u_name.strip().lower()
            unit_map = {
                "pa": units.pascal,
                "pascal": units.pascal,
                "pascals": units.pascal,
                "kpa": 1000 * units.pascal,
                "mpa": 1000000 * units.pascal,
                "bar": 100000 * units.pascal,
                "psi": 6894.757293168 * units.pascal,
                "atm": 101325 * units.pascal,
                "atmosphere": 101325 * units.pascal,
                "w": units.watt,
                "watt": units.watt,
                "watts": units.watt,
                "kw": 1000 * units.watt,
                "kilowatt": 1000 * units.watt,
                "hp": 745.69987158227022 * units.watt,
                "horsepower": 745.69987158227022 * units.watt,
                "j": units.joule,
                "joule": units.joule,
                "joules": units.joule,
                "kj": 1000 * units.joule,
                "cal": 4.184 * units.joule,
                "calorie": 4.184 * units.joule,
                "n": units.newton,
                "newton": units.newton,
                "lbf": 4.4482216152605 * units.newton,
                "m": units.meter,
                "meter": units.meter,
                "meters": units.meter,
                "km": 1000 * units.meter,
                "cm": 0.01 * units.meter,
                "mm": 0.001 * units.meter,
                "inch": 0.0254 * units.meter,
                "inches": 0.0254 * units.meter,
                "ft": 0.3048 * units.meter,
                "feet": 0.3048 * units.meter,
                "mi": 1609.344 * units.meter,
                "mile": 1609.344 * units.meter,
                "miles": 1609.344 * units.meter,
                "kg": units.kilogram,
                "kilogram": units.kilogram,
                "g": 0.001 * units.kilogram,
                "gram": 0.001 * units.kilogram,
                "lb": 0.45359237 * units.kilogram,
                "lbs": 0.45359237 * units.kilogram,
                "pound": 0.45359237 * units.kilogram,
                "s": units.second,
                "sec": units.second,
                "second": units.second,
                "seconds": units.second,
                "min": 60 * units.second,
                "minute": 60 * units.second,
                "hr": 3600 * units.second,
                "hour": 3600 * units.second,
                "hours": 3600 * units.second,
                "hz": units.hertz,
                "hertz": units.hertz,
                "v": units.volt,
                "volt": units.volt,
                "a": units.ampere,
                "amp": units.ampere,
                "ampere": units.ampere,
                "ohm": units.ohm,
                "ohms": units.ohm,
                "k": units.kelvin,
                "kelvin": units.kelvin,
            }
            if u_clean in unit_map:
                return unit_map[u_clean]
            if hasattr(units, u_clean):
                return getattr(units, u_clean)
            raise ValueError(f"Unknown unit: '{u_name}'")

        u_from = _resolve_unit(from_unit_str)
        u_to = _resolve_unit(to_unit_str)

        val_with_unit = quantity * u_from
        converted = units.convert_to(val_with_unit, u_to)
        # Extract numerical scalar
        numeric_res = float(converted / u_to)

        prob_latex = f"{quantity:g} \\text{{ {from_unit_str}}}"
        res_latex = f"{numeric_res:.6g} \\text{{ {to_unit_str}}}"

        return {
            "quantity": quantity,
            "from_unit": from_unit_str,
            "to_unit": to_unit_str,
            "result": numeric_res,
            "latex": f"{prob_latex} = {res_latex}",
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Physical Unit Conversion",
                problem_latex=prob_latex,
                steps=[
                    "Identified dimensional basis and scale factors.",
                    f"Converted ${from_unit_str}$ to target unit ${to_unit_str}$.",
                ],
                result_latex=res_latex,
            ),
        }


class FinancialMathSubsystem:
    """
    Financial and Quantitative Mathematics subsystem.
    Covers Time Value of Money (PV, FV, NPV, IRR), Loan Amortization,
    CAGR, WACC, DCF Valuation, and Corporate Financial metrics.
    """

    @staticmethod
    def cagr(
        beginning_value: float, ending_value: float, periods: float
    ) -> dict[str, Any]:
        if beginning_value <= 0 or ending_value <= 0 or periods <= 0:
            raise ValueError(
                "Beginning value, ending value, and periods must be positive for CAGR."
            )
        cagr_rate = ((ending_value / beginning_value) ** (1.0 / periods)) - 1.0
        cagr_pct = cagr_rate * 100.0

        prob_latex = f"\\text{{CAGR}} = \\left( \\frac{{{ending_value:,.2f}}}{{{beginning_value:,.2f}}} \\right)^{{\\frac{{1}}{{{periods}}}}} - 1"
        res_latex = f"{cagr_pct:.2f}\\% \\quad (\\text{{decimal: }} {cagr_rate:.6f})"

        steps = [
            f"Beginning Value: `${beginning_value:,.2f}$`",
            f"Ending Value: `${ending_value:,.2f}$` over `{periods}` periods.",
            "Formula: $\\text{CAGR} = (V_f / V_0)^{1/t} - 1$",
        ]

        return {
            "beginning_value": beginning_value,
            "ending_value": ending_value,
            "periods": periods,
            "cagr_rate": cagr_rate,
            "cagr_percent": cagr_pct,
            "latex": res_latex,
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Compound Annual Growth Rate (CAGR)",
                problem_latex=prob_latex,
                steps=steps,
                result_latex=res_latex,
            ),
        }

    @staticmethod
    def net_present_value(
        discount_rate: float, cash_flows: list[float]
    ) -> dict[str, Any]:
        """
        NPV = sum(CF_t / (1 + r)^t)
        cash_flows[0] is typically initial outflow (negative).
        """
        if discount_rate <= -1.0:
            raise ValueError("Discount rate must be greater than -100%.")

        npv_val = sum(
            cf / ((1.0 + discount_rate) ** t) for t, cf in enumerate(cash_flows)
        )

        terms = [
            f"\\frac{{{cf:,.2f}}}{{(1 + {discount_rate})^{{{t}}}}}"
            for t, cf in enumerate(cash_flows)
        ]
        prob_latex = "\\text{NPV} = " + " + ".join(terms)
        res_latex = f"\\${npv_val:,.2f}"

        steps = [
            f"Discount rate: `{discount_rate * 100:.2f}%`",
            f"Discounted each cash flow across {len(cash_flows)} periods.",
            f"Summed discounted cash flows: `${npv_val:,.2f}$`",
        ]

        return {
            "discount_rate": discount_rate,
            "cash_flows": cash_flows,
            "npv": npv_val,
            "latex": res_latex,
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Net Present Value (NPV)",
                problem_latex=prob_latex,
                steps=steps,
                result_latex=res_latex,
            ),
        }

    @staticmethod
    def internal_rate_of_return(
        cash_flows: list[float], precision: float = 1e-6, max_iter: int = 1000
    ) -> dict[str, Any]:
        """Calculates IRR via Newton-Raphson numerical root finding."""
        if not cash_flows or len(cash_flows) < 2:
            raise ValueError(
                "IRR requires at least 2 cash flows (an outflow and inflow)."
            )

        # Check for sign change
        has_pos = any(cf > 0 for cf in cash_flows)
        has_neg = any(cf < 0 for cf in cash_flows)
        if not (has_pos and has_neg):
            raise ValueError(
                "IRR requires at least one positive and one negative cash flow."
            )

        def _npv_and_deriv(r: float) -> tuple[float, float]:
            val = 0.0
            deriv = 0.0
            for t, cf in enumerate(cash_flows):
                denom = (1.0 + r) ** t
                val += cf / denom
                if t > 0:
                    deriv += -t * cf / ((1.0 + r) ** (t + 1))
            return val, deriv

        # Newton-Raphson iteration
        rate = 0.1  # Initial guess 10%
        for _ in range(max_iter):
            val, deriv = _npv_and_deriv(rate)
            if abs(val) < precision:
                break
            if abs(deriv) < 1e-12:
                rate += 0.01
                continue
            rate = rate - (val / deriv)

        irr_pct = rate * 100.0
        prob_latex = f"\\sum_{{t=0}}^{{{len(cash_flows) - 1}}} \\frac{{\\text{{CF}}_t}}{{(1 + \\text{{IRR}})^t}} = 0"
        res_latex = f"{irr_pct:.2f}\\% \\quad (\\text{{decimal: }} {rate:.6f})"

        steps = [
            f"Evaluated {len(cash_flows)} cash flow intervals with initial outlay ${cash_flows[0]:,.2f}$.",
            "Executed Newton-Raphson root solver to find discount rate yielding NPV = 0.",
            f"Calculated internal rate of return: `{irr_pct:.2f}%`",
        ]

        return {
            "cash_flows": cash_flows,
            "irr_rate": rate,
            "irr_percent": irr_pct,
            "latex": res_latex,
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Internal Rate of Return (IRR)",
                problem_latex=prob_latex,
                steps=steps,
                result_latex=res_latex,
            ),
        }

    @staticmethod
    def loan_amortization(
        principal: float,
        annual_rate: float,
        term_years: float,
        payments_per_year: int = 12,
    ) -> dict[str, Any]:
        """Calculates periodic loan payment (PMT), total interest, and total cost."""
        if principal <= 0 or annual_rate < 0 or term_years <= 0:
            raise ValueError("Principal, rate, and term must be positive numbers.")

        n_payments = int(term_years * payments_per_year)
        r_period = annual_rate / payments_per_year

        if r_period == 0:
            pmt = principal / n_payments
        else:
            pmt = (
                principal
                * (r_period * (1 + r_period) ** n_payments)
                / (((1 + r_period) ** n_payments) - 1)
            )

        total_paid = pmt * n_payments
        total_interest = total_paid - principal

        prob_latex = (
            f"\\text{{PMT}} = P \\cdot \\frac{{r(1+r)^n}}{{(1+r)^n - 1}} \\quad "
            f"(P=\\${principal:,.2f}, r={annual_rate * 100:.2f}\\%/\\text{{yr}}, n={n_payments})"
        )
        res_latex = f"\\text{{Periodic Payment: }} \\${pmt:,.2f} \\quad (\\text{{Total Interest: }} \\${total_interest:,.2f})"

        steps = [
            f"Loan Principal: `${principal:,.2f}`",
            f"Periodic Interest Rate: `{r_period * 100:.4f}%` across `{n_payments}` payments.",
            "Calculated standard amortization formula.",
            f"Total Interest Paid: `${total_interest:,.2f}` on total payment `${total_paid:,.2f}`.",
        ]

        return {
            "principal": principal,
            "annual_rate": annual_rate,
            "term_years": term_years,
            "payments_per_year": payments_per_year,
            "total_payments": n_payments,
            "periodic_payment": pmt,
            "total_paid": total_paid,
            "total_interest": total_interest,
            "latex": res_latex,
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Loan Payment & Amortization",
                problem_latex=prob_latex,
                steps=steps,
                result_latex=res_latex,
            ),
        }

    @staticmethod
    def wacc(
        equity: float,
        debt: float,
        cost_of_equity: float,
        cost_of_debt: float,
        tax_rate: float,
    ) -> dict[str, Any]:
        """Calculates Weighted Average Cost of Capital (WACC)."""
        total_val = equity + debt
        if total_val <= 0:
            raise ValueError("Total firm value (Equity + Debt) must be positive.")

        weight_e = equity / total_val
        weight_d = debt / total_val
        wacc_rate = (weight_e * cost_of_equity) + (
            weight_d * cost_of_debt * (1.0 - tax_rate)
        )
        wacc_pct = wacc_rate * 100.0

        prob_latex = "\\text{WACC} = \\left(\\frac{E}{V} \\cdot r_e\\right) + \\left(\\frac{D}{V} \\cdot r_d \\cdot (1 - t)\\right)"
        res_latex = f"{wacc_pct:.2f}\\% \\quad (\\text{{decimal: }} {wacc_rate:.6f})"

        steps = [
            f"Total Capital Value: $V = \\${total_val:,.2f}$ ($E/V = {weight_e * 100:.1f}\\%$, $D/V = {weight_d * 100:.1f}\\%$)",
            f"Cost of Equity: `{cost_of_equity * 100:.2f}%`, After-tax Cost of Debt: `{cost_of_debt * (1 - tax_rate) * 100:.2f}%`",
            "Calculated weighted sum.",
        ]

        return {
            "equity": equity,
            "debt": debt,
            "wacc_rate": wacc_rate,
            "wacc_percent": wacc_pct,
            "latex": res_latex,
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Weighted Average Cost of Capital (WACC)",
                problem_latex=prob_latex,
                steps=steps,
                result_latex=res_latex,
            ),
        }


class StatisticalNumericalSubsystem:
    """
    Statistical and Numerical Computation subsystem powered by SciPy and NumPy.
    Covers descriptive statistics, inferential hypothesis testing,
    correlation analysis, numerical quadrature, and non-linear curve fitting.
    """

    @staticmethod
    def _get_scipy_stats() -> Any:
        import scipy.stats

        return scipy.stats

    @staticmethod
    def _get_numpy() -> Any:
        import numpy

        return numpy

    @classmethod
    def descriptive_statistics(cls, data: list[float]) -> dict[str, Any]:
        if not data:
            raise ValueError("Data list cannot be empty for statistical analysis.")

        np = cls._get_numpy()
        arr = np.array(data, dtype=float)

        mean_val = float(np.mean(arr))
        median_val = float(np.median(arr))
        var_val = float(np.var(arr, ddof=1)) if len(arr) > 1 else 0.0
        std_val = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        q25, q75 = float(np.percentile(arr, 25)), float(np.percentile(arr, 75))
        iqr_val = q75 - q25

        prob_latex = f"N = {len(data)}, \\quad \\text{{Sample Range: }}[{min_val:g}, {max_val:g}]"
        res_latex = (
            f"\\mu = {mean_val:.4f}, \\quad \\sigma = {std_val:.4f}, \\quad "
            f"\\text{{Median}} = {median_val:.4f}, \\quad \\text{{IQR}} = {iqr_val:.4f}"
        )

        steps = [
            f"Calculated sample size: $N = {len(data)}$",
            f"Computed sample mean: $\\bar{{x}} = \\frac{{1}}{{N}}\\sum x_i = {mean_val:.4f}$",
            f"Computed sample standard deviation: $s = {std_val:.4f}$ with variance $s^2 = {var_val:.4f}$",
            f"Calculated quartiles: $Q_1 = {q25:.4f}$, $Q_2 = {median_val:.4f}$, $Q_3 = {q75:.4f}$",
        ]

        return {
            "count": len(data),
            "mean": mean_val,
            "median": median_val,
            "std_dev": std_val,
            "variance": var_val,
            "min": min_val,
            "max": max_val,
            "q25": q25,
            "q75": q75,
            "iqr": iqr_val,
            "latex": res_latex,
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title="Descriptive Statistical Analysis",
                problem_latex=prob_latex,
                steps=steps,
                result_latex=res_latex,
            ),
        }

    @classmethod
    def hypothesis_test(
        cls,
        test_type: str,
        sample1: list[float],
        sample2: list[float] | None = None,
        pop_mean: float = 0.0,
    ) -> dict[str, Any]:
        """
        Executes hypothesis testing:
        - '1samp_ttest': One-sample Student's t-test against pop_mean
        - '2samp_ttest': Two-sample independent t-test (Welch's t-test)
        - 'paired_ttest': Paired t-test
        """
        stats = cls._get_scipy_stats()
        t_type = test_type.lower().strip()

        if t_type in ("1samp_ttest", "one_sample_ttest", "ttest_1samp"):
            t_stat, p_val = stats.ttest_1samp(sample1, pop_mean)
            prob_latex = f"H_0: \\mu = {pop_mean:g} \\quad \\text{{vs.}} \\quad H_1: \\mu \\neq {pop_mean:g}"
            res_latex = f"t = {float(t_stat):.4f}, \\quad p = {float(p_val):.4e}"
            steps = [
                f"Evaluated sample of $N = {len(sample1)}$ against null hypothesized mean $\\mu_0 = {pop_mean}$.",
                f"Calculated Student's $t$-statistic: $t = {float(t_stat):.4f}$",
                f"Computed two-tailed $p$-value: $p = {float(p_val):.4e}$",
                "Statistically significant at $\\alpha = 0.05$"
                if p_val < 0.05
                else "Fail to reject $H_0$ at $\\alpha = 0.05$.",
            ]
            return {
                "test": "one_sample_ttest",
                "t_statistic": float(t_stat),
                "p_value": float(p_val),
                "significant_05": bool(p_val < 0.05),
                "latex": res_latex,
                "formatted_markdown": LaTeXStepFormatter.format_solution(
                    title="One-Sample Student's t-Test",
                    problem_latex=prob_latex,
                    steps=steps,
                    result_latex=res_latex,
                ),
            }

        elif t_type in ("2samp_ttest", "two_sample_ttest", "ttest_ind"):
            if not sample2:
                raise ValueError("Two-sample t-test requires both sample1 and sample2.")
            t_stat, p_val = stats.ttest_ind(sample1, sample2, equal_var=False)
            prob_latex = "H_0: \\mu_1 = \\mu_2 \\quad \\text{vs.} \\quad H_1: \\mu_1 \\neq \\mu_2 \\quad (\\text{Welch's } t\\text{-test})"
            res_latex = f"t = {float(t_stat):.4f}, \\quad p = {float(p_val):.4e}"
            steps = [
                f"Sample 1 ($N_1 = {len(sample1)}$) vs Sample 2 ($N_2 = {len(sample2)}$).",
                f"Calculated Welch's $t$-statistic: $t = {float(t_stat):.4f}$",
                f"Two-tailed $p$-value: $p = {float(p_val):.4e}$",
                "Statistically significant difference at $\\alpha = 0.05$"
                if p_val < 0.05
                else "No statistically significant difference at $\\alpha = 0.05$.",
            ]
            return {
                "test": "two_sample_ttest",
                "t_statistic": float(t_stat),
                "p_value": float(p_val),
                "significant_05": bool(p_val < 0.05),
                "latex": res_latex,
                "formatted_markdown": LaTeXStepFormatter.format_solution(
                    title="Two-Sample Independent t-Test (Welch's)",
                    problem_latex=prob_latex,
                    steps=steps,
                    result_latex=res_latex,
                ),
            }

        raise ValueError(f"Unsupported hypothesis test type: {test_type}")

    @classmethod
    def correlation(
        cls, x: list[float], y: list[float], method: str = "pearson"
    ) -> dict[str, Any]:
        if len(x) != len(y) or len(x) < 2:
            raise ValueError(
                "Arrays x and y must have equal length >= 2 for correlation."
            )

        stats = cls._get_scipy_stats()
        if method.lower() == "spearman":
            res = stats.spearmanr(x, y)
            name = "Spearman Rank Correlation"
            sym = "\\rho"
        else:
            res = stats.pearsonr(x, y)
            name = "Pearson Correlation"
            sym = "r"

        r_val = float(res.statistic)
        p_val = float(res.pvalue)

        prob_latex = f"N = {len(x)} \\text{{ paired observations}}"
        res_latex = f"{sym} = {r_val:.4f}, \\quad p = {p_val:.4e}"

        steps = [
            f"Calculated covariance and standard deviations across $N={len(x)}$ points.",
            f"Coefficient value: ${sym} = {r_val:.4f}$",
            f"Significance $p$-value: $p = {p_val:.4e}$",
        ]

        return {
            "method": method,
            "coefficient": r_val,
            "p_value": p_val,
            "latex": res_latex,
            "formatted_markdown": LaTeXStepFormatter.format_solution(
                title=name,
                problem_latex=prob_latex,
                steps=steps,
                result_latex=res_latex,
            ),
        }

    @classmethod
    def curve_fit(
        cls, model_type: str, x_data: list[float], y_data: list[float]
    ) -> dict[str, Any]:
        """Fits mathematical models (linear, polynomial, exponential) to data points."""
        if len(x_data) != len(y_data) or len(x_data) < 2:
            raise ValueError("x_data and y_data must have the same length >= 2.")

        np = cls._get_numpy()
        x_arr = np.array(x_data, dtype=float)
        y_arr = np.array(y_data, dtype=float)

        m_type = model_type.lower().strip()
        if m_type in ("linear", "line"):
            # y = a*x + b
            slope, intercept = np.polyfit(x_arr, y_arr, 1)
            y_pred = slope * x_arr + intercept
            ss_res = np.sum((y_arr - y_pred) ** 2)
            ss_tot = np.sum((y_arr - np.mean(y_arr)) ** 2)
            r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 1.0

            prob_latex = f"y = mx + c \\quad (N = {len(x_data)})"
            res_latex = f"y = {slope:.4f}x + {intercept:.4f} \\quad (R^2 = {r2:.4f})"

            steps = [
                "Performed ordinary least squares linear regression.",
                f"Calculated slope: $m = {slope:.4f}$",
                f"Calculated intercept: $c = {intercept:.4f}$",
                f"Coefficient of determination: $R^2 = {r2:.4f}$",
            ]

            return {
                "model_type": "linear",
                "slope": float(slope),
                "intercept": float(intercept),
                "r_squared": r2,
                "latex": res_latex,
                "formatted_markdown": LaTeXStepFormatter.format_solution(
                    title="Linear Regression Model",
                    problem_latex=prob_latex,
                    steps=steps,
                    result_latex=res_latex,
                ),
            }

        elif m_type in ("quadratic", "poly2"):
            a, b, c = np.polyfit(x_arr, y_arr, 2)
            y_pred = a * x_arr**2 + b * x_arr + c
            ss_res = np.sum((y_arr - y_pred) ** 2)
            ss_tot = np.sum((y_arr - np.mean(y_arr)) ** 2)
            r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 1.0

            prob_latex = f"y = ax^2 + bx + c \\quad (N = {len(x_data)})"
            res_latex = f"y = {a:.4f}x^2 + {b:.4f}x + {c:.4f} \\quad (R^2 = {r2:.4f})"

            return {
                "model_type": "quadratic",
                "coefficients": [float(a), float(b), float(c)],
                "r_squared": r2,
                "latex": res_latex,
                "formatted_markdown": LaTeXStepFormatter.format_solution(
                    title="Quadratic Polynomial Fit",
                    problem_latex=prob_latex,
                    steps=[
                        "Fitted 2nd degree polynomial via least squares.",
                        f"Obtained coefficients: $a={a:.4f}, b={b:.4f}, c={c:.4f}$.",
                    ],
                    result_latex=res_latex,
                ),
            }

        raise ValueError(f"Unsupported curve fitting model: {model_type}")


class MathEngine:
    """
    Unified Mathematical Computation Engine.
    Dispatches across Symbolic Math (SymPy), Financial Models,
    and Statistical/Numerical (SciPy/NumPy) subsystems with AST sandboxing.
    """

    def __init__(self) -> None:
        self.symbolic = SymbolicMathSubsystem()
        self.financial = FinancialMathSubsystem()
        self.stats = StatisticalNumericalSubsystem()

    def calculate(self, expression: str) -> dict[str, Any]:
        """Evaluates arbitrary algebraic, calculus, or arithmetic expressions symbolically and numerically."""
        return self.symbolic.evaluate_expression(expression)

    def execute_operation(
        self, operation: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Dynamic dispatch for structured multi-agent and tool tasks."""
        op = operation.lower().strip()

        # 1. Symbolic & Engineering Algebra/Calculus
        if op in ("solve", "solve_equation", "equation"):
            return self.symbolic.solve_equation(
                equation_str=params.get("equation", params.get("expression", "")),
                variable=params.get("variable", "x"),
            )
        elif op in ("solve_system", "system_of_equations"):
            return self.symbolic.solve_system(
                equations=params.get("equations", []),
                variables=params.get("variables", ["x", "y"]),
            )
        elif op in ("diff", "derivative", "differentiate"):
            return self.symbolic.differentiate(
                expression=params.get("expression", ""),
                variable=params.get("variable", "x"),
                order=int(params.get("order", 1)),
            )
        elif op in ("integrate", "integral"):
            return self.symbolic.integrate(
                expression=params.get("expression", ""),
                variable=params.get("variable", "x"),
                lower=params.get("lower"),
                upper=params.get("upper"),
            )
        elif op in ("limit", "lim"):
            return self.symbolic.limit(
                expression=params.get("expression", ""),
                variable=params.get("variable", "x"),
                target=params.get("target", 0),
                direction=params.get("direction", "+-"),
            )
        elif op in ("series", "taylor_series"):
            return self.symbolic.series_expansion(
                expression=params.get("expression", ""),
                variable=params.get("variable", "x"),
                point=params.get("point", 0),
                order=int(params.get("order", 6)),
            )
        elif op in ("ode", "solve_ode", "differential_equation"):
            return self.symbolic.solve_ode(
                ode_expression=params.get("ode", params.get("expression", "")),
                function_name=params.get("function_name", "y"),
                variable=params.get("variable", "x"),
                initial_conditions=params.get("initial_conditions"),
            )
        elif op in ("laplace", "laplace_transform"):
            return self.symbolic.laplace_transform(
                expression=params.get("expression", ""),
                t_var=params.get("t_var", "t"),
                s_var=params.get("s_var", "s"),
            )
        elif op in ("inv_laplace", "inverse_laplace", "inverse_laplace_transform"):
            return self.symbolic.inverse_laplace_transform(
                expression=params.get("expression", ""),
                s_var=params.get("s_var", "s"),
                t_var=params.get("t_var", "t"),
            )
        elif op in ("matrix", "matrix_operation", "matrix_operations"):
            return self.symbolic.matrix_operations(
                operation=params.get("sub_operation", params.get("matrix_op", "det")),
                matrix_a=params.get("matrix_a", params.get("matrix", [])),
                matrix_b=params.get("matrix_b"),
            )
        elif op in ("unit_convert", "convert_units", "units"):
            return self.symbolic.convert_units(
                quantity=float(params.get("quantity", 1.0)),
                from_unit_str=params.get("from_unit", ""),
                to_unit_str=params.get("to_unit", ""),
            )

        # 2. Financial & Business Models
        elif op in ("cagr", "growth_rate"):
            return self.financial.cagr(
                beginning_value=float(
                    params.get("beginning_value", params.get("old_value", 0))
                ),
                ending_value=float(
                    params.get("ending_value", params.get("new_value", 0))
                ),
                periods=float(params.get("periods", params.get("years", 1))),
            )
        elif op in ("npv", "net_present_value"):
            return self.financial.net_present_value(
                discount_rate=float(
                    params.get("discount_rate", params.get("rate", 0.1))
                ),
                cash_flows=[float(x) for x in params.get("cash_flows", [])],
            )
        elif op in ("irr", "internal_rate_of_return"):
            return self.financial.internal_rate_of_return(
                cash_flows=[float(x) for x in params.get("cash_flows", [])]
            )
        elif op in ("amortization", "loan", "pmt"):
            return self.financial.loan_amortization(
                principal=float(params.get("principal", 0)),
                annual_rate=float(params.get("annual_rate", params.get("rate", 0.05))),
                term_years=float(params.get("term_years", params.get("years", 30))),
                payments_per_year=int(params.get("payments_per_year", 12)),
            )
        elif op in ("wacc", "cost_of_capital"):
            return self.financial.wacc(
                equity=float(params.get("equity", 0)),
                debt=float(params.get("debt", 0)),
                cost_of_equity=float(params.get("cost_of_equity", 0.1)),
                cost_of_debt=float(params.get("cost_of_debt", 0.05)),
                tax_rate=float(params.get("tax_rate", 0.21)),
            )

        # 3. Statistical & Numerical Methods
        elif op in ("stats", "descriptive_stats", "statistics"):
            return self.stats.descriptive_statistics(
                data=[float(x) for x in params.get("data", params.get("values", []))]
            )
        elif op in ("ttest", "hypothesis_test"):
            return self.stats.hypothesis_test(
                test_type=params.get("test_type", "1samp_ttest"),
                sample1=[
                    float(x) for x in params.get("sample1", params.get("data", []))
                ],
                sample2=[float(x) for x in params.get("sample2", [])]
                if params.get("sample2")
                else None,
                pop_mean=float(params.get("pop_mean", 0.0)),
            )
        elif op in ("correlation", "corr"):
            return self.stats.correlation(
                x=[float(v) for v in params.get("x", [])],
                y=[float(v) for v in params.get("y", [])],
                method=params.get("method", "pearson"),
            )
        elif op in ("curve_fit", "regression"):
            return self.stats.curve_fit(
                model_type=params.get("model_type", "linear"),
                x_data=[float(v) for v in params.get("x", [])],
                y_data=[float(v) for v in params.get("y", [])],
            )

        # 4. Fallback to general symbolic expression evaluation
        if "expression" in params:
            return self.calculate(params["expression"])

        raise ValueError(f"Unknown mathematical operation: '{operation}'")
