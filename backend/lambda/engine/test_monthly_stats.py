"""Month-end close and median dollar volume."""

from __future__ import annotations

import unittest
from unittest.mock import patch

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

    def test_the_refresh_rewrites_the_previous_month_as_well_as_the_open_one(self) -> None:
        self.assertEqual(monthly_stats.months_to_refresh(["2017-01", "2017-02", "2017-03"]), ["2017-02", "2017-03"])
        self.assertEqual(monthly_stats.months_to_refresh(["2017-03"]), ["2017-03"])

    def test_a_name_that_cleared_the_floors_and_still_has_a_cik_is_priced(self) -> None:
        rows = [
            {"symbol": "SMALL", "monthEnd": "2018-06-29", "close": 20, "medianDollarVolume": 30_000_000},
            {"symbol": "GONE", "monthEnd": "2018-06-29", "close": 20, "medianDollarVolume": 30_000_000},
            {"symbol": "CHEAP", "monthEnd": "2018-06-29", "close": 1, "medianDollarVolume": 30_000_000},
            {"symbol": "EARLY", "monthEnd": "2016-06-30", "close": 20, "medianDollarVolume": 30_000_000},
        ]
        tickers = {
            "SMALL": {"cik": "0000000002", "name": "Small Co"},
            "CHEAP": {"cik": "0000000003", "name": "Cheap Co"},
            "EARLY": {"cik": "0000000004", "name": "Early Co"},
        }
        scope = monthly_stats.for_adjusted(["EXMPL"], tickers, rows=rows)
        self.assertEqual(scope["symbols"], ["EXMPL", "SMALL"])
        self.assertFalse(scope["monthlyStatsMissing"])
        reused = monthly_stats.for_adjusted(["EXMPL"], tickers, rows=rows, reused={"SMALL"})
        self.assertEqual(reused["symbols"], ["EXMPL"])

    def test_each_monthly_file_is_read_on_its_own_and_no_file_is_reported(self) -> None:
        files = {
            "prices/monthly/month=2017-02/stats.jsonl.gz": [
                {"symbol": "SMALL", "monthEnd": "2017-02-28", "close": 20, "medianDollarVolume": 30_000_000}
            ],
            "prices/monthly/month=2017-03/stats.jsonl.gz": [
                {"symbol": "LATER", "monthEnd": "2017-03-31", "close": 20, "medianDollarVolume": 30_000_000}
            ],
        }

        def read(_bucket: str, key: str, client: object = None) -> list[dict[str, object]]:
            del client
            return list(files[key])

        with (
            patch.dict("os.environ", {"DATA_BUCKET_NAME": "data"}),
            patch("s3io.list_keys", return_value=list(files)),
            patch("s3io.get_jsonl_gz", side_effect=read),
        ):
            found, missing = monthly_stats._covered_symbols("2017-02", None, 5, 20_000_000)
        self.assertEqual(found, {"SMALL", "LATER"})
        self.assertFalse(missing)
        with patch.dict("os.environ", {"DATA_BUCKET_NAME": "data"}), patch("s3io.list_keys", return_value=[]):
            empty, absent = monthly_stats._covered_symbols("2017-02", None, 5, 20_000_000)
        self.assertEqual(empty, set())
        self.assertTrue(absent)

    def test_months_run_from_the_start_through_the_end(self) -> None:
        self.assertEqual(
            monthly_stats.months_between("2016-11", "2017-02"), ["2016-11", "2016-12", "2017-01", "2017-02"]
        )


if __name__ == "__main__":
    unittest.main()
