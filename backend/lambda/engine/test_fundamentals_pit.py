"""Point-in-time rules, checked against hand arithmetic."""

from __future__ import annotations

import unittest

from fundamentals_pit import as_of, average_stock, latest_stock, ttm


def _flow(field: str, start: str, end: str, value: float, filed: str, form: str = "10-Q") -> dict:
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


class PointInTimeTest(unittest.TestCase):
    def test_a_filing_is_invisible_the_day_before(self) -> None:
        rows = [_flow("revenue", "2024-01-01", "2024-12-31", 100, "2025-02-15", "10-K")]
        self.assertEqual(as_of(rows, "2025-02-14"), [])
        self.assertEqual(len(as_of(rows, "2025-02-15")), 1)

    def test_a_restatement_applies_only_from_its_filing_date(self) -> None:
        original = _flow("revenue", "2024-01-01", "2024-03-31", 10, "2024-05-01")
        restated = _flow("revenue", "2024-01-01", "2024-03-31", 12, "2024-08-01", "10-Q/A")
        self.assertEqual(as_of([original, restated], "2024-07-01")[0]["value"], 10)
        self.assertEqual(as_of([original, restated], "2024-08-01")[0]["value"], 12)

    def test_ttm_is_the_year_right_after_the_ten_k(self) -> None:
        rows = [_flow("revenue", "2023-01-01", "2023-12-31", 400, "2024-02-20", "10-K")]
        self.assertEqual(ttm(as_of(rows, "2024-03-01"), "revenue"), 400)

    def test_ttm_after_the_first_quarter(self) -> None:
        # FY 400, Q1 this year 110, Q1 last year 90. TTM = 400 + 110 - 90 = 420.
        rows = [
            _flow("revenue", "2023-01-01", "2023-12-31", 400, "2024-02-20", "10-K"),
            _flow("revenue", "2023-01-01", "2023-03-31", 90, "2023-05-01"),
            _flow("revenue", "2024-01-01", "2024-03-31", 110, "2024-05-01"),
        ]
        self.assertEqual(ttm(as_of(rows, "2024-05-02"), "revenue"), 420)

    def test_ttm_after_the_third_quarter(self) -> None:
        # FY 400, nine months 330, prior nine months 280. TTM = 400 + 330 - 280 = 450.
        rows = [
            _flow("revenue", "2023-01-01", "2023-12-31", 400, "2024-02-20", "10-K"),
            _flow("revenue", "2023-01-01", "2023-09-30", 280, "2023-11-01"),
            _flow("revenue", "2024-01-01", "2024-09-30", 330, "2024-11-01"),
        ]
        self.assertEqual(ttm(as_of(rows, "2024-11-02"), "revenue"), 450)

    def test_a_september_fiscal_year(self) -> None:
        # FY ends 2023-09-30 = 500. Next quarter ends 2023-12-31 = 140.
        # Same quarter a year earlier ends 2022-12-31 = 100. TTM = 500 + 140 - 100 = 540.
        rows = [
            _flow("revenue", "2022-10-01", "2023-09-30", 500, "2023-11-15", "10-K"),
            _flow("revenue", "2022-10-01", "2022-12-31", 100, "2023-02-10"),
            _flow("revenue", "2023-10-01", "2023-12-31", 140, "2024-02-10"),
        ]
        self.assertEqual(ttm(as_of(rows, "2024-02-11"), "revenue"), 540)

    def test_a_missing_prior_year_value_is_none(self) -> None:
        rows = [
            _flow("revenue", "2023-01-01", "2023-12-31", 400, "2024-02-20", "10-K"),
            _flow("revenue", "2024-01-01", "2024-03-31", 110, "2024-05-01"),
        ]
        self.assertIsNone(ttm(as_of(rows, "2024-05-02"), "revenue"))

    def test_average_stock_needs_both_points(self) -> None:
        rows = [
            _stock("totalAssets", "2023-12-31", 80, "2024-02-20"),
            _stock("totalAssets", "2024-12-31", 120, "2025-02-20"),
        ]
        visible = as_of(rows, "2025-02-21")
        self.assertEqual(latest_stock(visible, "totalAssets"), 120)
        self.assertEqual(average_stock(visible, "totalAssets"), 100)
        self.assertIsNone(average_stock(as_of(rows, "2024-03-01"), "totalAssets"))


if __name__ == "__main__":
    unittest.main()
