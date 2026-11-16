"""Month-end close and median dollar volume."""

from __future__ import annotations

import unittest

import monthly_stats


class MonthlyStatsTest(unittest.TestCase):
    def test_the_month_keeps_the_last_close_and_the_median_dollar_volume(self) -> None:
        days = [
            ("2017-01-31", [{"symbol": "AAA", "close": 10, "volume": 100}, {"symbol": "BBB", "close": 5, "volume": 5}]),
            ("2017-02-01", [{"symbol": "AAA", "close": 20, "volume": 100}]),
            ("2017-02-28", [{"symbol": "AAA", "close": 30, "volume": 100}]),
        ]
        rows = monthly_stats.month_rows(days, "2017-02")
        self.assertEqual([row["symbol"] for row in rows], ["AAA"])
        self.assertEqual(rows[0]["monthEnd"], "2017-02-28")
        self.assertEqual(rows[0]["close"], 30)
        self.assertEqual(rows[0]["medianDollarVolume"], 2000)

    def test_months_run_from_the_start_through_the_end(self) -> None:
        self.assertEqual(
            monthly_stats.months_between("2016-11", "2017-02"), ["2016-11", "2016-12", "2017-01", "2017-02"]
        )


if __name__ == "__main__":
    unittest.main()
