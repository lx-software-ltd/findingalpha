"""Three days of headlines, one file per symbol and New York date."""

from __future__ import annotations

import unittest
from datetime import date

import alpaca_data
import ingest_fundamentals
import ingest_news
import ingest_prices
import s3io
from test_ingest_prices import _Bucket


def _story(story_id: int, created: str, symbols: list[str]) -> dict[str, object]:
    return {
        "id": story_id,
        "symbols": symbols,
        "headline": "Example rises",
        "summary": "Short",
        "source": "Example Wire",
        "url": "https://example.com/story",
        "createdAt": created,
    }


class NewsIngestTest(unittest.TestCase):
    def test_three_days_are_deduped_and_dated_in_new_york(self) -> None:
        bucket = _Bucket()
        seen: dict[str, str] = {}

        def fetch(symbols: list[str], start: str, end: str) -> list[dict[str, object]]:
            self.assertEqual(symbols, ["EXMPL", "SECND"])
            seen["start"] = start
            seen["end"] = end
            return [
                _story(7, "2024-06-04T03:30:00Z", ["EXMPL", "OTHER"]),
                _story(7, "2024-06-04T03:30:00Z", ["EXMPL", "OTHER"]),
                _story(8, "2024-06-04T15:00:00Z", ["SECND"]),
            ]

        result = ingest_news.daily(
            ["EXMPL", "SECND", " "],
            date(2024, 6, 4),
            fetch_news=fetch,
            bucket="data",
            client=bucket,
            ingest_enabled=lambda: True,
        )
        self.assertEqual(result, {"items": 2})
        self.assertTrue(seen["start"].startswith("2024-06-02"))
        self.assertTrue(seen["end"].startswith("2024-06-05"))
        early = list(s3io.get_jsonl_gz("data", "news/symbol=EXMPL/date=2024-06-03.jsonl.gz", client=bucket))
        later = list(s3io.get_jsonl_gz("data", "news/symbol=SECND/date=2024-06-04.jsonl.gz", client=bucket))
        empty = list(s3io.get_jsonl_gz("data", "news/symbol=EXMPL/date=2024-06-02.jsonl.gz", client=bucket))
        self.assertEqual([row["id"] for row in early], [7])
        self.assertEqual([row["id"] for row in later], [8])
        self.assertEqual(empty, [])
        self.assertNotIn(("data", "news/symbol=OTHER/date=2024-06-03.jsonl.gz"), bucket.objects)

    def test_no_symbols_and_ingest_off_make_no_request(self) -> None:
        def refuse(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
            raise AssertionError("requested")

        self.assertEqual(ingest_news.daily([], date(2024, 6, 4), fetch_news=refuse), {"items": 0})
        with self.assertRaises(ingest_news.IngestDisabled):
            ingest_news.daily(["EXMPL"], date(2024, 6, 4), fetch_news=refuse, ingest_enabled=lambda: False)

    def test_symbols_are_upper_cased_and_a_bad_time_is_skipped(self) -> None:
        bucket = _Bucket()
        seen: dict[str, list[str]] = {}

        def fetch(symbols: list[str], start: str, end: str) -> list[dict[str, object]]:
            del start, end
            seen["symbols"] = symbols
            return [
                _story(1, "not-a-date", ["EXMPL"]),
                _story(2, "2024-06-04T15:00:00Z", ["exmpl"]),
            ]

        result = ingest_news.daily(
            ["exmpl"],
            date(2024, 6, 4),
            fetch_news=fetch,
            bucket="data",
            client=bucket,
            ingest_enabled=lambda: True,
        )
        self.assertEqual(seen["symbols"], ["EXMPL"])
        self.assertEqual(result, {"items": 1})
        rows = list(s3io.get_jsonl_gz("data", "news/symbol=EXMPL/date=2024-06-04.jsonl.gz", client=bucket))
        self.assertEqual([row["id"] for row in rows], [2])

    def test_disabled_is_one_class(self) -> None:
        self.assertIs(ingest_prices.IngestDisabled, alpaca_data.IngestDisabled)
        self.assertIs(ingest_fundamentals.IngestDisabled, alpaca_data.IngestDisabled)
        self.assertIs(ingest_news.IngestDisabled, alpaca_data.IngestDisabled)


if __name__ == "__main__":
    unittest.main()
