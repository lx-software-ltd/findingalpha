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


if __name__ == "__main__":
    unittest.main()
