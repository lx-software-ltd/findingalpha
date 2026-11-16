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

    def test_the_screen_jobs_follow_the_ingest_switch(self) -> None:
        for name in ("screen", "backfill_monthly_stats", "backtest"):
            self.assertEqual(jobs_handler.switch_for(name), "ingestEnabled")
            self.assertIsNotNone(jobs_handler.handler_for(name))


if __name__ == "__main__":
    unittest.main()
