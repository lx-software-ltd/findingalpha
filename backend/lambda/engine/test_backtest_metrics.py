"""Hand-checked performance figures."""

from __future__ import annotations

import math
import unittest

import backtest_metrics


class BacktestMetricsTest(unittest.TestCase):
    def test_each_figure_matches_the_hand_calculation(self) -> None:
        curve = [100.0, 110.0, 121.0]
        self.assertAlmostEqual(backtest_metrics.cagr(curve) or 0, 1.21**6 - 1, delta=1e-12)
        self.assertAlmostEqual(backtest_metrics.annualised_volatility([0.1, -0.1]) or 0, 0.1 * math.sqrt(12))
        self.assertIsNone(backtest_metrics.sharpe([0.02, 0.02], [0.0, 0.0]))
        self.assertAlmostEqual(backtest_metrics.sharpe([0.02, 0.04], [0.01, 0.01]) or 0, 2 * math.sqrt(12))
        drawdown = backtest_metrics.max_drawdown([100.0, 120.0, 90.0, 150.0], ["a", "b", "c", "d"])
        self.assertAlmostEqual(drawdown["drawdown"], -0.25)
        self.assertEqual((drawdown["start"], drawdown["end"]), ("b", "c"))
        self.assertAlmostEqual(backtest_metrics.hit_rate([0.1, 0.1, 0.2], [0.0, 0.0, 0.3]) or 0, 2 / 3)
        window = backtest_metrics.worst_window([100.0, 110.0, 90.0, 80.0], ["a", "b", "c", "d"], months=2)
        self.assertIsNotNone(window)
        assert window is not None
        self.assertAlmostEqual(window["return"], 80 / 110 - 1)
        self.assertEqual(window["start"], "b")
        self.assertAlmostEqual(backtest_metrics.average_turnover([1, 0, 0.5]) or 0, 0.5)
        table = backtest_metrics.yearly_table(
            [100.0, 110.0, 90.0, 99.0],
            [100.0, 100.0, 100.0, 110.0],
            ["start", "2017-01", "2017-02", "2018-01"],
        )
        self.assertEqual(table[0]["year"], "2017")
        self.assertAlmostEqual(table[0]["strategy"], -0.1)
        self.assertAlmostEqual(table[1]["strategy"], 0.1)
        self.assertAlmostEqual(table[1]["benchmark"], 0.1)


if __name__ == "__main__":
    unittest.main()
