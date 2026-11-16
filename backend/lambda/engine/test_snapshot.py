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


if __name__ == "__main__":
    unittest.main()
