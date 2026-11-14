"""Job run rows."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import job_runs


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

    def test_skip_is_recorded(self) -> None:
        table = _Table()
        with patch("store.put", side_effect=lambda item: table.put_item(Item=item)):
            with job_runs.record("tick") as run:
                run.skip()
        self.assertEqual(table.items[-1]["status"], "skipped_disabled")


if __name__ == "__main__":
    unittest.main()
