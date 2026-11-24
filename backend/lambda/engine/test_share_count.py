"""Split dates and the order of share-count sources."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

import share_count

ON = date(2024, 6, 3)
_COVER = """
<xbrli:context id="class-a"><xbrli:period><xbrli:instant>2024-04-17</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="class-b"><xbrli:period><xbrli:instant>2024-04-17</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="old"><xbrli:period><xbrli:instant>2023-04-17</xbrli:instant></xbrli:period></xbrli:context>
<ix:nonFraction contextRef="class-a" name="dei:EntityCommonStockSharesOutstanding" scale="0">1,000</ix:nonFraction>
<ix:nonFraction contextRef="class-b" name="dei:EntityCommonStockSharesOutstanding" scale="0">40</ix:nonFraction>
<ix:nonFraction contextRef="old" name="dei:EntityCommonStockSharesOutstanding" scale="0">9,999</ix:nonFraction>
<ix:nonFraction contextRef="class-a" name="us-gaap:PreferredStockSharesOutstanding" scale="6">5</ix:nonFraction>
"""


def _split(ex: str, old: int, new: int) -> dict[str, object]:
    return {"exDate": ex, "splitFrom": old, "splitTo": new}


def _row(field: str, end: str, value: float, filed: str, *, tag: str, start: str | None = None) -> dict[str, object]:
    return {
        "field": field,
        "kind": "stock" if field == "sharesOutstanding" else "share",
        "tag": tag,
        "start": start or end,
        "end": end,
        "value": value,
        "filed": filed,
    }


class CoverAsOfTest(unittest.TestCase):
    def test_the_latest_cover_already_public_is_kept(self) -> None:
        payload = {
            "attempts": {
                "old": {"filed": "2017-03-01", "end": "2017-02-28", "value": 10},
                "new": {"filed": "2018-03-01", "end": "2018-02-28", "value": 40},
                "blank": {"filed": "2017-01-01", "end": "2016-12-31"},
            }
        }
        early = share_count.cover_as_of(payload, date(2017, 6, 1))
        later = share_count.cover_as_of(payload, date(2018, 6, 1))
        assert early is not None and later is not None
        self.assertEqual(early["value"], 10)
        self.assertEqual(later["value"], 40)
        self.assertIsNone(share_count.cover_as_of({"attempts": {"old": {"end": "2017-02-28", "value": 10}}}, ON))


class SplitFactorTest(unittest.TestCase):
    def test_splits_inside_the_window_multiply_and_the_edges_do_not(self) -> None:
        splits = [
            _split("2024-04-15", 1, 10),
            _split("2024-05-01", 2, 1),
            _split("2024-03-31", 1, 4),
            _split("2024-06-04", 1, 3),
        ]
        self.assertEqual(share_count.split_factor(splits, date(2024, 3, 31), ON), 5)
        self.assertEqual(share_count.split_factor([], ON, ON), 1)
        self.assertEqual(share_count.split_factor([_split("2024-04-01", 1, 10)], date(2024, 4, 1), ON), 1)


class ChooseTest(unittest.TestCase):
    def test_each_tag_uses_its_own_split_date(self) -> None:
        cover = _row("sharesOutstanding", "2024-03-31", 10, "2024-04-26", tag=share_count.COVER_TAG)
        sheet = _row("sharesOutstanding", "2024-03-31", 12, "2024-04-26", tag="CommonStockSharesOutstanding")
        cover_choice = share_count.choose([cover], ON)
        sheet_choice = share_count.choose([sheet], ON)
        assert cover_choice is not None and sheet_choice is not None
        self.assertEqual(cover_choice.after, date(2024, 3, 31))
        self.assertEqual(sheet_choice.after, date(2024, 4, 26))
        self.assertEqual(cover_choice.source, "cover")
        self.assertEqual(sheet_choice.source, "balanceSheet")

    def test_a_count_older_than_450_days_falls_through(self) -> None:
        fresh_end = (ON - timedelta(days=450)).isoformat()
        stale_end = (ON - timedelta(days=451)).isoformat()
        fresh = _row("sharesOutstanding", fresh_end, 10, "2024-05-01", tag="CommonStockSharesOutstanding")
        stale = _row("sharesOutstanding", stale_end, 99, "2024-05-01", tag="CommonStockSharesOutstanding")
        weighted = _row(
            "weightedDilutedShares",
            "2024-03-31",
            7,
            "2024-05-01",
            tag="WeightedAverageNumberOfDilutedSharesOutstanding",
            start="2024-01-01",
        )
        longer = _row(
            "weightedDilutedShares",
            "2024-03-31",
            8,
            "2024-05-01",
            tag="WeightedAverageNumberOfDilutedSharesOutstanding",
            start="2023-04-01",
        )
        fresh_choice = share_count.choose([fresh], ON)
        assert fresh_choice is not None
        self.assertEqual(fresh_choice.source, "balanceSheet")
        picked = share_count.choose([stale, weighted, longer], ON)
        assert picked is not None
        self.assertEqual(picked.source, "weightedDiluted")
        self.assertEqual(picked.value, 7)
        self.assertEqual(picked.after, date(2024, 5, 1))
        self.assertIsNone(share_count.choose([stale], ON))

    def test_the_adjusted_count_uses_the_split_date(self) -> None:
        sheet = _row("sharesOutstanding", "2024-03-31", 100, "2024-04-26", tag="CommonStockSharesOutstanding")
        splits = [_split("2024-04-15", 1, 10)]
        adjusted = share_count.shares_as_of([sheet], splits, ON)
        assert adjusted is not None
        self.assertEqual(adjusted["shares"], 100)
        self.assertEqual(adjusted["source"], "balanceSheet")
        cover = {"filed": "2024-04-24", "end": "2024-04-17", "value": 40}
        fallen = share_count.shares_as_of([], splits, ON, cover=cover)
        assert fallen is not None
        self.assertEqual(fallen["shares"], 40)
        self.assertEqual(fallen["source"], "coverClasses")


class CoverPageTest(unittest.TestCase):
    def test_classes_on_the_latest_instant_are_added(self) -> None:
        parsed = share_count.parse_cover_shares(_COVER)
        assert parsed is not None
        self.assertEqual(parsed["end"], "2024-04-17")
        self.assertEqual(parsed["value"], 1040)
        scaled = (
            '<xbrli:context id="m"><xbrli:instant>2024-05-01</xbrli:instant></xbrli:context>'
            '<ix:nonFraction contextRef="m" name="dei:EntityCommonStockSharesOutstanding" scale="6">5</ix:nonFraction>'
        )
        scaled_cover = share_count.parse_cover_shares(scaled)
        assert scaled_cover is not None
        self.assertEqual(scaled_cover["value"], 5_000_000)
        self.assertIsNone(share_count.parse_cover_shares("<html></html>"))

    def test_a_company_wide_total_is_not_added_to_the_classes(self) -> None:
        document = """
        <xbrli:context id="total"><xbrli:period><xbrli:instant>2024-04-17</xbrli:instant></xbrli:period></xbrli:context>
        <xbrli:context id="class-a"><xbrli:entity><xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">A</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2024-04-17</xbrli:instant></xbrli:period></xbrli:context>
        <ix:nonFraction contextRef="total" name="dei:EntityCommonStockSharesOutstanding" scale="0">100</ix:nonFraction>
        <ix:nonFraction contextRef="class-a" name="dei:EntityCommonStockSharesOutstanding" scale="0">60</ix:nonFraction>
        """
        parsed = share_count.parse_cover_shares(document)
        assert parsed is not None
        self.assertEqual(parsed["value"], 100)


if __name__ == "__main__":
    unittest.main()
