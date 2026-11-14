"""Hand-worked factor and composite examples."""

from __future__ import annotations

import math
import unittest

import composite
import factors_quality
import factors_trend
import factors_value


class FactorTest(unittest.TestCase):
    def test_roic_uses_the_default_tax_rate_when_pretax_is_not_positive(self) -> None:
        # NOPAT = 100 * (1 - 0.21) = 79. Invested capital 200. ROIC = 0.395.
        self.assertAlmostEqual(factors_quality.roic(100, None, -5, 200, max_tax_rate=0.35, default_tax_rate=0.21), 0.395)

    def test_roic_clamps_the_tax_rate(self) -> None:
        # Tax 50 / pretax 100 = 0.5, clamped to 0.35. NOPAT = 65. Capital 100. ROIC = 0.65.
        self.assertAlmostEqual(factors_quality.roic(100, 50, 100, 100, max_tax_rate=0.35, default_tax_rate=0.21), 0.65)

    def test_missing_input_is_none(self) -> None:
        self.assertIsNone(factors_quality.fcf_margin(10, None, 20))
        self.assertIsNone(factors_value.earnings_yield(10, None))
        self.assertIsNone(factors_quality.accruals(None, 1, 1))

    def test_net_debt_is_none_when_ebitda_is_not_positive(self) -> None:
        self.assertIsNone(factors_quality.net_debt_to_ebitda(10, 0, 0, -5, 1))

    def test_interest_coverage_caps_and_treats_zero_debt_as_the_cap(self) -> None:
        self.assertEqual(factors_quality.interest_coverage(50, 0, 0, coverage_cap=100), 100)
        self.assertEqual(factors_quality.interest_coverage(500, 1, 10, coverage_cap=100), 100)
        self.assertIsNone(factors_quality.interest_coverage(50, 0, 10, coverage_cap=100))

    def test_enterprise_value_rejects_non_positive(self) -> None:
        self.assertIsNone(factors_value.enterprise_value(10, 0, 0, 20))
        self.assertEqual(factors_value.fcf_yield(15, factors_value.enterprise_value(100, 20, 5, 25)), 15 / 100)

    def test_momentum_and_the_moving_average(self) -> None:
        closes: list[float | None] = [100.0] * 252 + [121.0]
        # t-252 is index 0 (value 100), t-21 is index 231 (value 100). momentum = 0.
        self.assertEqual(factors_trend.momentum_12_1(closes), 0)
        rising = [float(index) for index in range(1, 201)]
        self.assertAlmostEqual(factors_trend.above_sma200(rising) or 0, 200 / (sum(rising) / 200) - 1)
        self.assertIsNone(factors_trend.volatility_252([100.0] * 10))

    def test_volatility_of_a_flat_price_is_zero(self) -> None:
        self.assertEqual(factors_trend.volatility_252([100.0] * 253), 0)

    def test_winsorise_uses_linear_percentiles(self) -> None:
        clipped = composite.winsorise([1, 2, 3, 4, 100], 0, 100)
        self.assertEqual(clipped[0], 1)
        self.assertEqual(clipped[-1], 100)
        inner = composite.winsorise([1, 2, 3, 4, 100], 50, 50)
        self.assertTrue(all(value == 3 for value in inner if value is not None))

    def test_a_small_sector_uses_the_universe(self) -> None:
        values = [1.0, 3.0, 5.0]
        scores = composite.zscores(values, ["a", "a", "b"], min_sector_size=3)
        mean = 3
        deviation = math.sqrt(((1 - 3) ** 2 + 0 + (5 - 3) ** 2) / 3)
        self.assertAlmostEqual(scores[0] or 0, (1 - mean) / deviation)

    def test_composite_is_none_when_a_group_is_missing(self) -> None:
        self.assertIsNone(composite.composite({"quality": 1.0, "value": None}, {"quality": 0.5, "value": 0.5}))
        self.assertAlmostEqual(composite.composite({"quality": 1.0, "value": 0.0}, {"quality": 0.4, "value": 0.6}) or 0, 0.4)


if __name__ == "__main__":
    unittest.main()
