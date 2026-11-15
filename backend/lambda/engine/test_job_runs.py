"""Job run rows."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import job_runs
from botocore.exceptions import BotoCoreError, NoRegionError
from config import MissingSetting


class _Table:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def put_item(self, *, Item: dict) -> None:
        self.items.append(dict(Item))


class JobRunsTest(unittest.TestCase):
    def test_success_writes_running_then_succeeded(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with job_runs.record("tick") as run:
                self.assertEqual(run.status, "running")
        self.assertEqual([item["status"] for item in table.items], ["running", "succeeded"])
        self.assertEqual(table.items[-1]["gsi1pk"], "JOBRUNS")
        self.assertIn("expiresAt", table.items[-1])

    def test_failure_records_the_error_class_and_reraises(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with self.assertRaises(RuntimeError):
                with job_runs.record("tick"):
                    raise RuntimeError("boom")
        self.assertEqual(table.items[-1]["status"], "failed")
        self.assertEqual(table.items[-1]["errorClass"], "RuntimeError")
        self.assertNotIn("Traceback", table.items[-1]["errorMessage"])

    def test_a_storage_error_on_write_does_not_fail_the_job(self) -> None:
        for error in (BotoCoreError(), NoRegionError(), MissingSetting("RECORDS_TABLE_NAME")):
            with self.subTest(error=type(error).__name__):
                with patch("store.put", side_effect=error), patch("job_runs._log_event") as log:
                    with job_runs.record("tick") as run:
                        self.assertEqual(run.status, "running")
                self.assertEqual(run.status, "succeeded")
                self.assertEqual(log.call_count, 2)
                log.assert_called_with("warning", tag="job_run_write_failed", job="tick", error=type(error).__name__)

    def test_a_storage_error_on_write_keeps_the_job_error(self) -> None:
        with patch("store.put", side_effect=BotoCoreError()), patch("job_runs._log_event"):
            with self.assertRaises(RuntimeError):
                with job_runs.record("tick"):
                    raise RuntimeError("boom")

    def test_skip_is_recorded(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with job_runs.record("tick") as run:
                run.skip()
        self.assertEqual(table.items[-1]["status"], "skipped_disabled")


if __name__ == "__main__":
    unittest.main()
