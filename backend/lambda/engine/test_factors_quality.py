"""Quality factors, checked against arithmetic written out here."""

from __future__ import annotations

import unittest

import factors_quality

_TAX = {"maxTaxRate": 0.35, "defaultTaxRate": 0.21}
_CAP = {"coverageCap": 100}


def _capital(**overrides: float | None) -> dict:
    base: dict = {
        "equity_avg": 0,
        "longTermDebt_avg": 0,
        "shortTermDebt_avg": 0,
        "cash_avg": 0,
    }
    base.update(overrides)
    return base


class QualityFactorTest(unittest.TestCase):
    def test_roic_uses_the_default_tax_rate_when_pretax_is_not_positive(self) -> None:
        # NOPAT = 100 * (1 - 0.21) = 79. Invested capital 200. ROIC = 0.395.
        snapshot = _capital(equity_avg=200)
        snapshot.update(operatingIncome_ttm=100, incomeTax_ttm=None, pretaxIncome_ttm=-5)
        self.assertAlmostEqual(factors_quality.roic(snapshot, _TAX) or 0, 0.395)

    def test_roic_clamps_the_tax_rate(self) -> None:
        # Tax 50 / pretax 100 = 0.5, clamped to 0.35. NOPAT = 65. Capital 100. ROIC = 0.65.
        snapshot = _capital(equity_avg=100)
        snapshot.update(operatingIncome_ttm=100, incomeTax_ttm=50, pretaxIncome_ttm=100)
        self.assertAlmostEqual(factors_quality.roic(snapshot, _TAX) or 0, 0.65)

    def test_roic_is_none_when_a_required_input_or_the_capital_is_missing(self) -> None:
        self.assertIsNone(factors_quality.roic(_capital(equity_avg=100), _TAX))
        self.assertIsNone(factors_quality.roic({"operatingIncome_ttm": 10, "equity_avg": 10}, _TAX))
        self.assertIsNone(factors_quality.roic({**_capital(), "operatingIncome_ttm": 10}, _TAX))

    def test_missing_gross_profit_uses_revenue_minus_cost(self) -> None:
        # (80 - 30) / 100 = 0.5.
        snapshot = {"grossProfit_ttm": None, "revenue_ttm": 80, "costOfRevenue_ttm": 30, "totalAssets_avg": 100}
        self.assertEqual(factors_quality.gross_profitability(snapshot, {}), 0.5)
        self.assertIsNone(factors_quality.gross_profitability({"revenue_ttm": 80, "totalAssets_avg": 100}, {}))
        self.assertIsNone(factors_quality.gross_profitability({"grossProfit_ttm": 10, "totalAssets_avg": 0}, {}))

    def test_missing_input_is_none(self) -> None:
        self.assertIsNone(factors_quality.fcf_margin({"operatingCashFlow_ttm": 10, "revenue_ttm": 20}, {}))
        self.assertIsNone(factors_quality.accruals({"operatingCashFlow_ttm": 1, "totalAssets_avg": 1}, {}))
        self.assertIsNone(
            factors_quality.fcf_margin({"operatingCashFlow_ttm": 10, "capex_ttm": 1, "revenue_ttm": 0}, {})
        )

    def test_free_cash_flow_is_the_difference(self) -> None:
        snapshot = {"operatingCashFlow_ttm": 15, "capex_ttm": 4}
        self.assertEqual(factors_quality.free_cash_flow_ttm(snapshot, {}), 11)
        self.assertIsNone(factors_quality.free_cash_flow_ttm({"operatingCashFlow_ttm": 15}, {}))

    def test_net_debt_is_none_when_ebitda_is_not_positive(self) -> None:
        snapshot = {
            "longTermDebt": 10,
            "shortTermDebt": 0,
            "cash": 0,
            "operatingIncome_ttm": -5,
            "depreciationAmortization_ttm": 1,
        }
        self.assertIsNone(factors_quality.net_debt_to_ebitda(snapshot, {}))

    def test_net_cash_is_a_negative_ratio(self) -> None:
        # Debt 0, cash 30, EBITDA 10. Net debt / EBITDA = -3.
        snapshot = {
            "longTermDebt": 0,
            "shortTermDebt": 0,
            "cash": 30,
            "operatingIncome_ttm": 8,
            "depreciationAmortization_ttm": 2,
        }
        self.assertEqual(factors_quality.net_debt_to_ebitda(snapshot, {}), -3)

    def test_interest_coverage_caps_and_treats_zero_debt_as_the_cap(self) -> None:
        zero_debt = {"operatingIncome_ttm": 50, "interestExpense_ttm": 0, "longTermDebt": 0, "shortTermDebt": 0}
        capped = {"operatingIncome_ttm": 500, "interestExpense_ttm": 1, "longTermDebt": 10, "shortTermDebt": 0}
        missing = {"operatingIncome_ttm": 50, "interestExpense_ttm": 0, "longTermDebt": 10, "shortTermDebt": 0}
        self.assertEqual(factors_quality.interest_coverage(zero_debt, _CAP), 100)
        self.assertEqual(factors_quality.interest_coverage(capped, _CAP), 100)
        self.assertIsNone(factors_quality.interest_coverage(missing, _CAP))
        absent = {"operatingIncome_ttm": 50, "longTermDebt": 0, "shortTermDebt": 0}
        self.assertEqual(factors_quality.interest_coverage(absent, _CAP), 100)


if __name__ == "__main__":
    unittest.main()
