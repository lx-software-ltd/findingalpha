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

    def test_a_continuing_chunk_is_partial(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with job_runs.record("backfill_prices") as run:
                job_runs.apply_result(run, {"ok": True, "status": "running", "cursor": 9, "total": 131})
        saved = table.items[-1]
        self.assertEqual(saved["status"], "partial")
        self.assertEqual(saved["errorMessage"], "9 of 131, continues on the next tick")
        self.assertNotIn("errorClass", saved)

    def test_a_pause_without_a_cursor_still_says_it_continues(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with job_runs.record("weekly_refresh") as run:
                job_runs.apply_result(run, {"ok": True, "status": "paused"})
        self.assertEqual(table.items[-1]["status"], "partial")
        self.assertEqual(table.items[-1]["errorMessage"], "continues on the next tick")

    def test_missing_inputs_is_a_failure(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with job_runs.record("weekly_refresh") as run:
                job_runs.apply_result(run, {"ok": False, "status": "missing_inputs"})
        saved = table.items[-1]
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["errorClass"], "missing_inputs")
        self.assertEqual(saved["errorMessage"], "missing inputs")

    def test_a_day_that_is_not_ready_is_partial(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with job_runs.record("ingest_daily") as run:
                job_runs.apply_result(run, {"ok": True, "status": "not_ready"})
        self.assertEqual(table.items[-1]["status"], "partial")
        self.assertEqual(table.items[-1]["errorMessage"], "continues on the next tick")

    def test_a_decimal_cursor_is_a_plain_integer(self) -> None:
        from decimal import Decimal

        self.assertEqual(
            job_runs.position({"status": "running", "cursor": Decimal("11"), "total": Decimal("131")}),
            {"status": "running", "cursor": 11, "total": 131},
        )

    def test_a_finished_chunk_stays_succeeded(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with job_runs.record("backfill_prices") as run:
                job_runs.apply_result(run, {"ok": True, "status": "done", "cursor": 131, "total": 131})
        self.assertEqual(table.items[-1]["status"], "succeeded")
        self.assertNotIn("errorMessage", table.items[-1])

    def test_an_unchanged_result_is_a_plain_success_for_another_job(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with job_runs.record("screen") as run:
                job_runs.apply_result(run, {"ok": True, "status": "unchanged", "failedKeys": ["a.pdf"]})
        self.assertEqual(table.items[-1]["status"], "succeeded")
        self.assertNotIn("errorMessage", table.items[-1])

    def test_an_evaluation_result_keeps_its_message(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with job_runs.record("kb_eval") as run:
                job_runs.apply_result(run, {"ok": True, "status": "done", "message": "2 of 3 at 8, 1 of 3 at 3"})
        self.assertEqual(table.items[-1]["status"], "succeeded")
        self.assertEqual(table.items[-1]["errorMessage"], "2 of 3 at 8, 1 of 3 at 3")


if __name__ == "__main__":
    unittest.main()
