"""The snapshot keeps facts and prices that were not yet public out of the inputs."""

from __future__ import annotations

import unittest
from datetime import date

import snapshot


def _flow(field: str, start: str, end: str, value: float, filed: str, form: str = "10-K") -> dict:
    return {
        "field": field,
        "kind": "flow",
        "start": start,
        "end": end,
        "value": value,
        "filed": filed,
        "form": form,
        "fy": None,
        "fp": None,
    }


def _stock(field: str, end: str, value: float, filed: str) -> dict:
    return {
        "field": field,
        "kind": "stock",
        "start": end,
        "end": end,
        "value": value,
        "filed": filed,
        "form": "10-Q",
        "fy": None,
        "fp": None,
    }


class SnapshotTest(unittest.TestCase):
    def test_a_later_bar_and_a_later_filing_stay_out(self) -> None:
        rows = [
            _flow("revenue", "2023-01-01", "2023-12-31", 10, "2024-02-01"),
            _flow("revenue", "2024-01-01", "2024-12-31", 99, "2025-02-01"),
            _stock("longTermDebt", "2023-12-31", 40, "2024-02-01"),
            _stock("shortTermDebt", "2023-12-31", 10, "2024-02-01"),
            _stock("cash", "2023-12-31", 20, "2024-02-01"),
            _stock("longTermDebt", "2024-12-31", 400, "2025-02-01"),
        ]
        bars = [
            {"date": "2024-06-01", "close": 5},
            {"date": date(2024, 6, 2), "close": 9},
        ]
        built = snapshot.build("AAA", "0000000001", date(2024, 6, 1), rows, bars, 5, 2)
        self.assertEqual(built["closes"], [5])
        self.assertEqual(built["revenue_ttm"], 10)
        self.assertEqual(built["longTermDebt"], 40)
        self.assertEqual(built["marketCap"], 10)
        # 10 + 40 + 10 - 20 = 40.
        self.assertEqual(built["enterpriseValue"], 40)
        self.assertEqual(built["asOf"], "2024-06-01")

    def test_a_non_positive_enterprise_value_is_none(self) -> None:
        rows = [
            _stock("longTermDebt", "2023-12-31", 0, "2024-02-01"),
            _stock("shortTermDebt", "2023-12-31", 0, "2024-02-01"),
            _stock("cash", "2023-12-31", 30, "2024-02-01"),
        ]
        built = snapshot.build("AAA", "1", "2024-06-01", rows, [], 10, 1)
        self.assertEqual(built["marketCap"], 10)
        self.assertIsNone(built["enterpriseValue"])

    def test_a_missing_debt_tag_is_zero_when_the_balance_sheet_exists(self) -> None:
        rows = [
            _stock("equity", "2023-12-31", 80, "2024-02-01"),
            _stock("cash", "2023-12-31", 20, "2024-02-01"),
            _stock("equity", "2024-12-31", 90, "2025-02-01"),
            _stock("cash", "2024-12-31", 20, "2025-02-01"),
            _stock("longTermDebt", "2024-12-31", 40, "2025-02-01"),
        ]
        built = snapshot.build("AAA", "1", "2025-03-01", rows, [], 10, 10)
        self.assertEqual(built["shortTermDebt"], 0)
        self.assertEqual(built["longTermDebt"], 40)
        # Prior statement has no debt tag, so its short-term and long-term debt count as zero.
        self.assertEqual(built["shortTermDebt_avg"], 0)
        self.assertEqual(built["longTermDebt_avg"], 20)
        self.assertEqual(built["enterpriseValue"], 100 + 40 + 0 - 20)

    def test_closes_follow_sessions_and_a_duplicate_date_keeps_the_later_bar(self) -> None:
        bars = [
            {"date": "2024-06-03", "close": 10},
            {"date": "2024-06-03", "close": 12},
            {"date": "2024-06-05", "close": 30},
        ]
        sessions = ["2024-06-03", "2024-06-04", "2024-06-05"]
        built = snapshot.build("AAA", "1", "2024-06-05", [], bars, None, None, sessions)
        self.assertEqual(built["closes"], [12, 12, 30])
        plain = snapshot.build("AAA", "1", "2024-06-05", [], bars, None, None)
        self.assertEqual(plain["closes"], [12, 30])

    def test_debt_omitted_from_a_later_statement_is_zero(self) -> None:
        rows = [
            _stock("longTermDebt", "2019-12-31", 500, "2020-02-15"),
            _stock("cash", "2019-12-31", 10, "2020-02-15"),
            _stock("equity", "2019-12-31", 100, "2020-02-15"),
            _stock("cash", "2023-12-31", 50, "2024-02-15"),
            _stock("equity", "2023-12-31", 900, "2024-02-15"),
        ]
        built = snapshot.build("AAA", "1", "2024-06-01", rows, [], 10, 10)
        self.assertEqual(built["longTermDebt"], 0)
        self.assertEqual(built["shortTermDebt"], 0)
        self.assertEqual(built["enterpriseValue"], 100 + 0 + 0 - 50)


if __name__ == "__main__":
    unittest.main()
