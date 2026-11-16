"""Point-in-time rules, checked against hand arithmetic."""

from __future__ import annotations

import unittest

from fundamentals_pit import as_of, average_stock, latest_stock, load_tag_maps, normalise, ttm


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

    def test_ttm_uses_the_year_to_date_when_the_quarter_shares_its_end(self) -> None:
        def both(order: str) -> list[dict]:
            quarter = _flow("revenue", "2024-04-01", "2024-06-30", 120, "2024-08-01")
            half = _flow("revenue", "2024-01-01", "2024-06-30", 230, "2024-08-01")
            prior_half = _flow("revenue", "2023-01-01", "2023-06-30", 190, "2023-08-01")
            year = _flow("revenue", "2023-01-01", "2023-12-31", 400, "2024-02-20", "10-K")
            pair = [quarter, half] if order == "quarter-first" else [half, quarter]
            return [year, prior_half, *pair]

        # FY 400, six months 230, prior six months 190. TTM = 400 + 230 - 190 = 440.
        for order in ("quarter-first", "half-first"):
            self.assertEqual(ttm(as_of(both(order), "2024-08-02"), "revenue"), 440)
        nine = [
            _flow("revenue", "2023-01-01", "2023-12-31", 400, "2024-02-20", "10-K"),
            _flow("revenue", "2023-01-01", "2023-09-30", 295, "2023-11-01"),
            _flow("revenue", "2024-07-01", "2024-09-30", 125, "2024-11-01"),
            _flow("revenue", "2024-01-01", "2024-09-30", 355, "2024-11-01"),
        ]
        # FY 400, nine months 355, prior nine months 295. TTM = 460, not the quarter.
        self.assertEqual(ttm(as_of(nine, "2024-11-02"), "revenue"), 460)

    def test_a_mid_year_quarter_alone_does_not_replace_the_year(self) -> None:
        rows = [
            _flow("revenue", "2023-01-01", "2023-12-31", 400, "2024-02-20", "10-K"),
            _flow("revenue", "2024-04-01", "2024-06-30", 120, "2024-08-01"),
        ]
        self.assertEqual(ttm(as_of(rows, "2024-08-02"), "revenue"), 400)

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


def _fact(end: str, value: float, filed: str, form: str = "10-K", start: str | None = None) -> dict:
    row = {"end": end, "val": value, "filed": filed, "form": form, "fy": 2024, "fp": "FY"}
    if start is not None:
        row["start"] = start
    return row


class NormaliseTest(unittest.TestCase):
    def test_the_contract_prefers_the_planned_tags(self) -> None:
        maps = load_tag_maps()
        self.assertEqual(maps["flows"]["revenue"][0], "Revenues")
        self.assertEqual(maps["stocks"]["sharesOutstanding"][0], "dei:EntityCommonStockSharesOutstanding")
        self.assertEqual(
            maps["shareFlows"]["weightedDilutedShares"], ["WeightedAverageNumberOfDilutedSharesOutstanding"]
        )
        self.assertIn("currentAssets", maps["stocks"])

    def test_the_first_tag_with_a_row_wins(self) -> None:
        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": [_fact("2024-12-31", 10, "2025-02-01", start="2024-01-01")]}},
                    "SalesRevenueNet": {"units": {"USD": [_fact("2024-12-31", 99, "2025-02-01", start="2024-01-01")]}},
                    "AssetsCurrent": {"units": {"USD": [_fact("2024-12-31", 40, "2025-02-01")]}},
                },
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [_fact("2024-12-31", 1000, "2025-02-01")]}
                    }
                },
            }
        }
        maps = {
            "flows": {"revenue": ["Revenues", "SalesRevenueNet"]},
            "stocks": {
                "currentAssets": ["AssetsCurrent"],
                "sharesOutstanding": ["dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"],
            },
        }
        rows = normalise(facts, maps)
        revenue = [row for row in rows if row["field"] == "revenue"]
        self.assertEqual([row["value"] for row in revenue], [10])
        assets = next(row for row in rows if row["field"] == "currentAssets")
        self.assertEqual(assets["kind"], "stock")
        shares = next(row for row in rows if row["field"] == "sharesOutstanding")
        self.assertEqual(shares["value"], 1000)
        self.assertEqual(shares["tag"], "dei:EntityCommonStockSharesOutstanding")

    def test_other_units_forms_and_lengths_are_dropped(self) -> None:
        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "EUR": [_fact("2024-12-31", 5, "2025-02-01", start="2024-01-01")],
                            "USD": [
                                _fact("2024-12-31", 8, "2025-02-01", "8-K", start="2024-01-01"),
                                _fact("2024-02-01", 3, "2025-02-01", start="2024-01-01"),
                            ],
                        }
                    }
                }
            }
        }
        rows = normalise(facts, {"flows": {"revenue": ["Revenues"]}, "stocks": {"cash": ["Cash"]}})
        self.assertEqual(rows, [])

    def test_a_later_tag_fills_a_period_the_first_tag_misses(self) -> None:
        def fact(start: str, end: str, value: float, filed: str) -> dict:
            return {"start": start, "end": end, "val": value, "filed": filed, "form": "10-K", "fy": 2024, "fp": "FY"}

        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": [fact("2017-01-01", "2017-12-31", 300, "2018-02-20")]}},
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {"USD": [fact("2023-01-01", "2023-12-31", 900, "2024-02-20")]}
                    },
                }
            }
        }
        maps = {
            "flows": {"revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]},
            "stocks": {"cash": ["Cash"]},
        }
        rows = normalise(facts, maps)
        visible = as_of(rows, "2024-03-01")
        self.assertEqual(sorted(row["end"] for row in visible), ["2017-12-31", "2023-12-31"])
        self.assertEqual(ttm(visible, "revenue"), 900)

    def test_share_classes_filed_together_are_added_and_a_later_filing_replaces_them(self) -> None:
        first = _stock("sharesOutstanding", "2024-02-01", 5_000_000_000, "2024-02-15")
        second = _stock("sharesOutstanding", "2024-02-01", 6_000_000_000, "2024-02-15")
        repeated = _stock("sharesOutstanding", "2024-02-01", 6_000_000_000, "2024-02-15")
        visible = as_of([first, second, repeated], "2024-03-01")
        self.assertEqual(latest_stock(visible, "sharesOutstanding"), 11_000_000_000)
        restated = _stock("sharesOutstanding", "2024-02-01", 12_000_000_000, "2024-05-01")
        self.assertEqual(
            latest_stock(as_of([first, second, restated], "2024-05-01"), "sharesOutstanding"), 12_000_000_000
        )

    def test_two_weighted_average_durations_stay_separate(self) -> None:
        facts = {
            "facts": {
                "us-gaap": {
                    "WeightedAverageNumberOfDilutedSharesOutstanding": {
                        "units": {
                            "shares": [
                                _fact("2024-03-31", 7, "2024-05-01", start="2024-01-01"),
                                _fact("2024-03-31", 8, "2024-05-01", start="2023-04-01"),
                            ]
                        }
                    }
                }
            }
        }
        rows = normalise(
            facts, {"shareFlows": {"weightedDilutedShares": ["WeightedAverageNumberOfDilutedSharesOutstanding"]}}
        )
        visible = as_of(rows, "2024-06-01")
        self.assertEqual(sorted(row["value"] for row in visible), [7, 8])
        self.assertTrue(all(row["kind"] == "share" for row in visible))

    def test_the_bundled_debt_roles_match_the_stock_tags(self) -> None:
        maps = load_tag_maps()
        roles = {tag for tags in maps["debt"].values() for tag in tags}
        self.assertEqual(roles, set(maps["stocks"]["longTermDebt"] + maps["stocks"]["shortTermDebt"]))

    def test_inclusive_long_term_debt_does_not_count_the_current_portion_twice(self) -> None:
        facts = _debt_facts(
            {
                "LongTermDebt": 100,
                "LongTermDebtCurrent": 30,
                "ShortTermBorrowings": 5,
            }
        )
        rows = normalise(facts, _debt_maps())
        self.assertEqual(_debt_value(rows, "longTermDebt"), 70)
        self.assertEqual(_debt_value(rows, "shortTermDebt"), 35)

    def test_debt_current_is_not_added_to_the_current_portion(self) -> None:
        facts = _debt_facts(
            {
                "LongTermDebtNoncurrent": 80,
                "LongTermDebtCurrent": 10,
                "DebtCurrent": 25,
                "ShortTermBorrowings": 15,
            }
        )
        rows = normalise(facts, _debt_maps())
        self.assertEqual(_debt_value(rows, "longTermDebt"), 80)
        self.assertEqual(_debt_value(rows, "shortTermDebt"), 25)

    def test_a_missing_debt_tag_is_left_missing(self) -> None:
        facts = _debt_facts({"LongTermDebt": 40, "Assets": 100})
        rows = normalise(facts, _debt_maps())
        self.assertEqual(_debt_value(rows, "longTermDebt"), 40)
        self.assertIsNone(_debt_value(rows, "shortTermDebt"))


def _debt_maps() -> dict:
    return {
        "flows": {"revenue": ["Revenues"]},
        "stocks": {
            "totalAssets": ["Assets"],
            "longTermDebt": ["LongTermDebtNoncurrent", "LongTermDebt"],
            "shortTermDebt": ["DebtCurrent", "LongTermDebtCurrent", "ShortTermBorrowings"],
        },
        "debt": {
            "noncurrent": ["LongTermDebtNoncurrent"],
            "includingCurrent": ["LongTermDebt"],
            "currentPortion": ["LongTermDebtCurrent"],
            "debtCurrent": ["DebtCurrent"],
            "borrowings": ["ShortTermBorrowings"],
        },
    }


def _debt_facts(values: dict[str, float]) -> dict:
    units = {
        tag: {"units": {"USD": [{"end": "2024-12-31", "val": value, "filed": "2025-02-01", "form": "10-K"}]}}
        for tag, value in values.items()
    }
    return {"facts": {"us-gaap": units}}


def _debt_value(rows: list[dict], field: str) -> float | None:
    matched = [row["value"] for row in rows if row["field"] == field]
    if not matched:
        return None
    return matched[0]


if __name__ == "__main__":
    unittest.main()
