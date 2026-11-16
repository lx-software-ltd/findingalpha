"""Value factors, checked against arithmetic written out here."""

from __future__ import annotations

import unittest

import factors_value


class ValueFactorTest(unittest.TestCase):
    def test_earnings_yield_rejects_a_missing_or_non_positive_value(self) -> None:
        self.assertIsNone(factors_value.earnings_yield({"operatingIncome_ttm": 10}, {}))
        self.assertIsNone(factors_value.earnings_yield({"operatingIncome_ttm": 10, "enterpriseValue": 0}, {}))
        self.assertIsNone(factors_value.earnings_yield({"operatingIncome_ttm": 10, "enterpriseValue": -1}, {}))

    def test_free_cash_flow_yield(self) -> None:
        # (15 - 0) / 100 = 0.15. Enterprise value is already on the snapshot.
        snapshot = {"operatingCashFlow_ttm": 15, "capex_ttm": 0, "enterpriseValue": 100}
        self.assertEqual(factors_value.fcf_yield(snapshot, {}), 0.15)
        self.assertIsNone(factors_value.fcf_yield({"operatingCashFlow_ttm": 15, "enterpriseValue": 100}, {}))


if __name__ == "__main__":
    unittest.main()
