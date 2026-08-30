import pytest
from app.core.math.engine import FinancialMathSubsystem, StatisticalNumericalSubsystem


def test_financial_cagr():
    res = FinancialMathSubsystem.cagr(beginning_value=100.0, ending_value=200.0, periods=5.0)
    assert pytest.approx(res["cagr_percent"], rel=1e-3) == 14.8698
    assert "formatted_markdown" in res


def test_financial_npv():
    # Initial outlay 1000, inflows 400, 400, 400 at 10%
    res = FinancialMathSubsystem.net_present_value(discount_rate=0.10, cash_flows=[-1000, 400, 400, 400])
    assert pytest.approx(res["npv"], rel=1e-3) == -5.2592


def test_financial_irr():
    # Outlay 100, inflows 50, 60, 70
    res = FinancialMathSubsystem.internal_rate_of_return(cash_flows=[-100, 50, 60, 70])
    assert res["irr_percent"] > 0
    assert pytest.approx(res["irr_percent"], rel=1e-2) == 33.87


def test_financial_loan_amortization():
    # $100,000 at 6% for 30 years
    res = FinancialMathSubsystem.loan_amortization(principal=100000, annual_rate=0.06, term_years=30)
    assert pytest.approx(res["periodic_payment"], rel=1e-2) == 599.55
    assert res["total_payments"] == 360


def test_financial_wacc():
    res = FinancialMathSubsystem.wacc(equity=600000, debt=400000, cost_of_equity=0.12, cost_of_debt=0.06, tax_rate=0.25)
    # WACC = 0.6 * 0.12 + 0.4 * 0.06 * 0.75 = 0.072 + 0.018 = 0.090 (9.0%)
    assert pytest.approx(res["wacc_percent"], rel=1e-3) == 9.0


def test_statistical_descriptive_stats():
    data = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    res = StatisticalNumericalSubsystem.descriptive_statistics(data)
    assert res["count"] == 10
    assert res["mean"] == 55.0
    assert res["median"] == 55.0
    assert res["min"] == 10.0
    assert res["max"] == 100.0


def test_statistical_hypothesis_ttest():
    sample = [5.1, 5.2, 4.9, 5.0, 5.3, 5.1, 4.8, 5.2]
    res = StatisticalNumericalSubsystem.hypothesis_test("1samp_ttest", sample1=sample, pop_mean=5.0)
    assert "t_statistic" in res
    assert "p_value" in res


def test_statistical_correlation():
    x = [1, 2, 3, 4, 5]
    y = [2, 4, 6, 8, 10]
    res = StatisticalNumericalSubsystem.correlation(x, y, method="pearson")
    assert pytest.approx(res["coefficient"], rel=1e-5) == 1.0


def test_statistical_curve_fit():
    x = [1, 2, 3, 4, 5]
    y = [3, 5, 7, 9, 11]  # y = 2x + 1
    res = StatisticalNumericalSubsystem.curve_fit("linear", x_data=x, y_data=y)
    assert pytest.approx(res["slope"], rel=1e-5) == 2.0
    assert pytest.approx(res["intercept"], rel=1e-5) == 1.0
    assert pytest.approx(res["r_squared"], rel=1e-5) == 1.0
