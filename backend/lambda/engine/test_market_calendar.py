"""The trading calendar is cached by year."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import market_calendar
import s3io
from test_s3io import _Bucket


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


if __name__ == "__main__":
    unittest.main()
