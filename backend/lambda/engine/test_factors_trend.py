"""Trend factors, checked against arithmetic written out here."""

from __future__ import annotations

import unittest

import factors_trend


class TrendFactorTest(unittest.TestCase):
    def test_momentum_and_the_moving_average(self) -> None:
        closes: list[float | None] = []
        closes.extend([100.0] * 252)
        closes.append(121.0)
        # t-252 and t-21 are both 100. Momentum is 0.
        self.assertEqual(factors_trend.momentum_12_1({"closes": closes}, {}), 0)
        rising = [float(index) for index in range(1, 201)]
        self.assertAlmostEqual(factors_trend.above_sma200({"closes": rising}, {}) or 0, 200 / (sum(rising) / 200) - 1)
        self.assertIsNone(factors_trend.volatility_252({"closes": [100.0] * 10}, {}))

    def test_a_missing_price_and_a_zero_past_price_are_none(self) -> None:
        closes: list[float | None] = [100.0] * 253
        closes[-22] = None
        self.assertIsNone(factors_trend.momentum_12_1({"closes": closes}, {}))
        closes[-22] = 100.0
        closes[0] = 0.0
        self.assertIsNone(factors_trend.momentum_12_1({"closes": closes}, {}))

    def test_volatility_of_a_flat_price_is_zero(self) -> None:
        self.assertEqual(factors_trend.volatility_252({"closes": [100.0] * 253}, {}), 0)

    def test_a_zero_average_is_none(self) -> None:
        self.assertIsNone(factors_trend.above_sma200({"closes": [0.0] * 200}, {}))


if __name__ == "__main__":
    unittest.main()
