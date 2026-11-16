"""Job dispatch."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import jobs_handler


class JobsHandlerTest(unittest.TestCase):
    def test_unknown_job(self) -> None:
        result = jobs_handler.lambda_handler({"job": "missing"}, None)
        self.assertFalse(result["ok"])

    def test_tick_records_a_run(self) -> None:
        with patch("job_runs.record") as record, patch("chunked.resume_stalled", return_value=[]):
            record.return_value.__enter__.return_value = type(
                "Run", (), {"status": "running", "skip": lambda self: None}
            )()
            result = jobs_handler.lambda_handler({"job": "tick"}, None)
        self.assertTrue(result["ok"])
        record.assert_called_once_with("tick")

    def test_a_switched_off_job_is_skipped(self) -> None:
        class Run:
            def skip(self) -> None:
                self.skipped = True

        run = Run()
        jobs_handler.SWITCHES["tick"] = "ingestEnabled"
        try:
            with patch("job_runs.record") as record, patch("kill_switch.is_enabled", return_value=False):
                record.return_value.__enter__.return_value = run
                result = jobs_handler.lambda_handler({"job": "tick"}, None)
        finally:
            jobs_handler.SWITCHES.pop("tick", None)
        self.assertEqual(result["status"], "skipped_disabled")
        self.assertTrue(run.skipped)

    def test_a_running_result_is_stored_as_partial(self) -> None:
        saved: list[dict] = []

        def handler(_event: dict, _run: object, _context: object) -> dict:
            return {"ok": True, "status": "running", "cursor": 1, "total": 4}

        with (
            patch.dict(jobs_handler.JOBS, {"tick": handler}),
            patch("store.put", side_effect=lambda item: saved.append(dict(item))),
        ):
            result = jobs_handler.lambda_handler({"job": "tick"}, None)
        self.assertEqual(result["status"], "running")
        self.assertEqual(saved[-1]["status"], "partial")
        self.assertEqual(saved[-1]["errorMessage"], "1 of 4, continues on the next tick")

    def test_a_monthly_failure_does_not_fail_the_weekly_refresh(self) -> None:
        with (
            patch("ingest_jobs.weekly_refresh", return_value={"ok": True, "status": "done"}),
            patch("monthly_stats.append_latest", side_effect=RuntimeError("slow")),
        ):
            result = jobs_handler._weekly({}, None, None)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["monthly"]["status"], "failed")

    def test_monthly_stats_wait_when_the_weekly_job_is_almost_out_of_time(self) -> None:
        class Clock:
            def get_remaining_time_in_millis(self) -> int:
                return 1000

        with patch("ingest_jobs.weekly_refresh", return_value={"ok": True, "status": "done"}):
            result = jobs_handler._weekly({}, None, Clock())
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["monthly"]["status"], "deferred")

    def test_monthly_stats_run_while_adjusted_prices_are_still_refreshing(self) -> None:
        with (
            patch(
                "ingest_jobs.weekly_refresh",
                return_value={"ok": True, "status": "running", "build": {"status": "done"}},
            ),
            patch("monthly_stats.append_latest", return_value={"ok": True, "status": "done"}) as append,
        ):
            result = jobs_handler._weekly({}, None, None)
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["monthly"]["status"], "done")
        append.assert_called_once()

    def test_monthly_stats_wait_until_the_universe_build_finishes(self) -> None:
        with (
            patch(
                "ingest_jobs.weekly_refresh",
                return_value={"ok": True, "status": "running", "build": {"status": "running"}},
            ),
            patch("monthly_stats.append_latest", side_effect=AssertionError("too early")) as append,
        ):
            result = jobs_handler._weekly({}, None, None)
        self.assertEqual(result["status"], "running")
        self.assertNotIn("monthly", result)
        append.assert_not_called()

    def test_monthly_stats_run_again_when_the_adjusted_refresh_finishes(self) -> None:
        with (
            patch("ingest_jobs.resume_adjusted", return_value={"ok": True, "status": "done"}),
            patch("monthly_stats.append_latest", return_value={"ok": True, "status": "done"}),
        ):
            result = jobs_handler._adjusted({}, None, None)
        self.assertEqual(result["monthly"]["status"], "done")

    def test_the_screen_jobs_follow_the_ingest_switch(self) -> None:
        for name in ("screen", "backfill_monthly_stats", "backtest"):
            self.assertEqual(jobs_handler.switch_for(name), "ingestEnabled")
            self.assertIsNotNone(jobs_handler.handler_for(name))


if __name__ == "__main__":
    unittest.main()
