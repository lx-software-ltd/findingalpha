"""The ingest jobs keep a saved window and resume a universe build."""

from __future__ import annotations

import unittest
from datetime import date, datetime

import ingest_jobs

DAY = date(2024, 6, 3)
NOON = datetime(2024, 6, 4, 12, tzinfo=ingest_jobs.NEW_YORK)


class IngestJobsTest(unittest.TestCase):
    def test_a_closed_session_does_no_work(self) -> None:
        def refuse(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("called")

        result = ingest_jobs.ingest_daily(
            {},
            None,
            now=NOON,
            sessions=[date(2024, 6, 4)],
            raw=refuse,
            actions=refuse,
            filings=refuse,
            headlines=refuse,
        )
        self.assertEqual(result["status"], "skipped_no_session")

    def test_the_daily_job_refreshes_corporate_actions(self) -> None:
        seen: dict[str, object] = {}

        def actions(start: date, end: date, sessions: list[date]) -> None:
            seen["window"] = (start, end, sessions)

        ingest_jobs.ingest_daily(
            {"params": {"day": "2024-06-03"}},
            None,
            sessions=[DAY],
            symbols=["EXMPL"],
            ciks=["0000000001"],
            raw=lambda *_args: None,
            actions=actions,
            filings=lambda *_args, **_kwargs: None,
            headlines=lambda *_args: None,
        )
        self.assertEqual(seen["window"], (date(2024, 5, 27), DAY, [DAY]))

    def test_a_resumed_backfill_keeps_the_saved_end(self) -> None:
        seen: dict[str, str] = {}

        def run(start: str, end: str, _sessions: list[date], _context: object, *, symbols: list[str]) -> dict[str, str]:
            seen["start"] = start
            seen["end"] = end
            seen["symbols"] = ",".join(symbols)
            return {"status": "running"}

        result = ingest_jobs.backfill_prices(
            {"params": {"start": "2016-01-01", "end": "2024-06-03", "symbols": ["EXMPL"]}},
            None,
            now=datetime(2024, 6, 10, 12, tzinfo=ingest_jobs.NEW_YORK),
            sessions=[DAY],
            run=run,
        )
        self.assertEqual(result["end"], "2024-06-03")
        self.assertEqual(seen["end"], "2024-06-03")
        self.assertEqual(seen["symbols"], "EXMPL")

    def test_a_finished_universe_refresh_builds_that_date(self) -> None:
        built: dict[str, object] = {}

        def refresh(_ciks: list[str], _context: object, *, job: str, as_of: str | None = None) -> dict[str, str]:
            self.assertEqual(job, ingest_jobs.UNIVERSE_REFRESH_JOB)
            self.assertEqual(as_of, "2024-06-03")
            return {"status": "done"}

        def build(day: str, _context: object, **kwargs: object) -> dict[str, object]:
            built["day"] = day
            built["assets"] = kwargs["assets"]
            return {"status": "done", "members": 1}

        result = ingest_jobs.resume_universe(
            {"params": {"ciks": ["0000000001"], "asOf": "2024-06-03", "assets": [{"symbol": "EXMPL"}]}},
            None,
            refresh=refresh,
            build=build,
        )
        self.assertEqual(built["day"], "2024-06-03")
        self.assertEqual(result["build"]["members"], 1)

    def test_tick_can_name_a_filings_refresh(self) -> None:
        import jobs_handler

        self.assertIs(jobs_handler.handler_for("ingest_filings_refresh#2024-06-03"), jobs_handler._filings)
        self.assertEqual(jobs_handler.switch_for("ingest_filings_refresh#2024-06-03"), "ingestEnabled")


if __name__ == "__main__":
    unittest.main()
