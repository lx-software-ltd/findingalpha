"""The dashboard read of the knowledge base."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import kb_status


class _Store:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}

    def get(self, pk: str, sk: str) -> dict | None:
        return self.rows.get((pk, sk))

    def put(self, item: dict) -> None:
        self.rows[(item["pk"], item["sk"])] = item


class KbStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _Store()
        patch("kb_status.store.get", self.store.get).start()
        patch("kb_status.timeutil.utc_now", lambda: datetime(2026, 11, 18, tzinfo=timezone.utc)).start()
        patch.dict("os.environ", {"KB_MAX_RAW_BYTES": "2147483648"}).start()

    def tearDown(self) -> None:
        patch.stopall()

    def test_an_empty_base_reports_zeros(self) -> None:
        payload = kb_status.status_payload()
        self.assertEqual(payload["documents"], 0)
        self.assertEqual(payload["status"], "never")
        self.assertEqual(payload["retrievals"], 0)
        self.assertEqual(payload["retrievalCap"], 5000)
        self.assertEqual(payload["capBytes"], 2147483648)
        self.assertEqual(payload["cost"], {"storageUsd": 0.0, "retrievalUsd": 0.0})
        self.assertIsNone(payload["blockedReason"])
        self.assertIsNone(payload["progress"])
        self.assertEqual(kb_status.eval_payload()["results"], [])

    def test_status_counts_size_retrievals_and_problems(self) -> None:
        self.store.put(
            {
                "pk": "KB#state",
                "sk": "META",
                "documents": 131,
                "bytes": 500_000_000,
                "status": "done",
                "syncedAt": "2026-11-18T01:00:00.000Z",
                "jobs": {"theory/": "job-1"},
                "problems": [
                    {"key": "theory/scan.pdf", "problem": "too_large"},
                    {"key": "theory/notes.rtf", "problem": "unsupported"},
                    {"key": "theory/skip.pdf", "problem": "mystery"},
                ],
                "failedKeys": ["theory/broken.pdf"],
                "blocked": {
                    "status": "blocked_deletion",
                    "deletions": [{"prefix": "theory/", "gone": 20, "previous": 100}],
                },
            }
        )
        self.store.put({"pk": "USAGE#2026-11", "sk": "KB", "count": 2500})
        self.store.put(
            {
                "pk": "KB#eval",
                "sk": "LATEST",
                "ranAt": "2026-11-18T02:00:00.000Z",
                "questions": 20,
                "hitAt8": 16,
                "hitAt3": 12,
                "results": [{"id": "q01", "rank": 2, "documents": ["secret.pdf"]}],
            }
        )
        payload = kb_status.status_payload()
        self.assertEqual(payload["documents"], 131)
        self.assertTrue(payload["running"])
        self.assertEqual(payload["retrievals"], 2500)
        self.assertEqual(payload["cost"]["storageUsd"], 2.5)
        self.assertEqual(payload["cost"]["retrievalUsd"], 2.5)
        self.assertNotIn("totalUsd", payload["cost"])
        self.assertIsNone(payload["progress"])
        self.assertEqual(
            payload["problems"],
            [
                {"key": "theory/scan.pdf", "problem": "too_large"},
                {"key": "theory/notes.rtf", "problem": "unsupported"},
            ],
        )
        self.assertEqual(payload["failedDocuments"], ["theory/broken.pdf"])
        self.assertIn("theory/", payload["blockedReason"])
        self.assertEqual(payload["evaluation"]["hitAt8"], 16)
        latest = kb_status.eval_payload()
        self.assertEqual(latest["results"], [{"id": "q01", "rank": 2}])
        self.assertNotIn("documents", json.dumps(latest["results"][0]))

    def test_dynamodb_decimals_stay_whole_numbers(self) -> None:
        from decimal import Decimal

        self.store.put(
            {
                "pk": "KB#state",
                "sk": "META",
                "documents": Decimal("131"),
                "bytes": Decimal("500000000"),
                "status": "running",
                "jobs": {"theory/": "job-1"},
                "progress": {"scanned": Decimal("12"), "indexed": Decimal("4"), "failed": Decimal("1")},
                "blocked": {
                    "status": "blocked_deletion",
                    "deletions": [{"prefix": "theory/", "gone": Decimal("20"), "previous": Decimal("100")}],
                },
            }
        )
        self.store.put({"pk": "USAGE#2026-11", "sk": "KB", "count": Decimal("2500")})
        self.store.put(
            {
                "pk": "KB#eval",
                "sk": "LATEST",
                "questions": Decimal("20"),
                "hitAt8": Decimal("16"),
                "hitAt3": Decimal("12"),
                "results": [{"id": "q01", "rank": Decimal("2"), "documents": ["secret.pdf"]}],
            }
        )
        payload = kb_status.status_payload()
        json.dumps(payload)
        self.assertEqual(payload["documents"], 131)
        self.assertEqual(payload["retrievals"], 2500)
        self.assertIsInstance(payload["retrievals"], int)
        self.assertEqual(payload["progress"], {"scanned": 12, "indexed": 4, "failed": 1})
        self.assertIsInstance(payload["evaluation"]["hitAt8"], int)
        self.assertEqual(payload["blockedReason"], "More than 15% of a folder is gone: theory/ lost 20 of 100.")
        latest = kb_status.eval_payload()
        json.dumps(latest)
        self.assertEqual(latest["results"], [{"id": "q01", "rank": 2}])
        self.assertIsInstance(latest["results"][0]["rank"], int)
