"""The trading calendar is cached by year."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import market_calendar
import s3io
from test_s3io import _Bucket

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


class MarketCalendarTest(unittest.TestCase):
    def test_sessions_are_cached_and_the_previous_session_can_be_last_year(self) -> None:
        bucket = _Bucket()
        fetched: list[int] = []

        def fetch_year(year: int) -> list[str]:
            fetched.append(year)
            if year == 2024:
                return ["2024-12-31"]
            return ["2025-01-02", "2025-01-03"]

        with patch("config.data_bucket_name", return_value="data"):
            days = market_calendar.sessions(date(2024, 12, 1), date(2025, 1, 31), fetch_year, client=bucket)
            again = market_calendar.sessions(date(2025, 1, 1), date(2025, 1, 31), fetch_year, client=bucket)
            previous = market_calendar.previous_session(date(2025, 1, 1), fetch_year, client=bucket)
        self.assertEqual(days, [date(2024, 12, 31), date(2025, 1, 2), date(2025, 1, 3)])
        self.assertEqual(again, [date(2025, 1, 2), date(2025, 1, 3)])
        self.assertEqual(previous, date(2024, 12, 31))
        self.assertEqual(fetched, [2024, 2025])
        self.assertTrue(s3io.exists("data", "reference/calendar/year=2024.json", client=bucket))

    def test_an_empty_year_is_not_cached(self) -> None:
        bucket = _Bucket()
        fetched: list[int] = []

        def fetch_year(year: int) -> list[str]:
            fetched.append(year)
            return []

        with patch("config.data_bucket_name", return_value="data"):
            market_calendar.sessions(date(2024, 1, 1), date(2024, 1, 2), fetch_year, client=bucket, now=NOW)
            market_calendar.sessions(date(2024, 1, 1), date(2024, 1, 2), fetch_year, client=bucket, now=NOW)
        self.assertEqual(fetched, [2024, 2024])
        self.assertFalse(s3io.exists("data", "reference/calendar/year=2024.json", client=bucket))

    def test_the_current_year_is_refetched_after_a_day(self) -> None:
        bucket = _Bucket()
        s3io.put_json(
            "data",
            "reference/calendar/year=2026.json",
            {"sessions": ["2026-01-02"], "fetchedAt": "2026-11-13T00:00:00.000Z"},
            client=bucket,
        )
        fetched: list[int] = []

        def fetch_year(year: int) -> list[str]:
            fetched.append(year)
            return ["2026-01-02", "2026-01-05"]

        with patch("config.data_bucket_name", return_value="data"):
            days = market_calendar.sessions(date(2026, 1, 1), date(2026, 1, 31), fetch_year, client=bucket, now=NOW)
            again = market_calendar.sessions(date(2026, 1, 1), date(2026, 1, 31), fetch_year, client=bucket, now=NOW)
        self.assertEqual(days, [date(2026, 1, 2), date(2026, 1, 5)])
        self.assertEqual(again, days)
        self.assertEqual(fetched, [2026])

    def test_the_alpaca_calendar_route_returns_session_dates(self) -> None:
        class Client:
            def __init__(self) -> None:
                self.url = ""

            def _json(self, url: str) -> list[dict[str, str]]:
                self.url = url
                return [{"date": "2024-06-03"}, {"closed": True}]

        client = Client()
        with patch("alpaca_data._open", return_value=client):
            days = market_calendar.fetch_alpaca_year(2024)
        self.assertEqual(days, ["2024-06-03"])
        self.assertIn("/v2/calendar", client.url)
        self.assertIn("start=2024-01-01", client.url)
        self.assertIn("end=2024-12-31", client.url)


if __name__ == "__main__":
    unittest.main()
