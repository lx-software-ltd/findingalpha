"""Knowledge base sync decisions, with a stubbed Bedrock client."""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import kb_sync

NOW = datetime(2026, 11, 18, 2, 30, tzinfo=timezone.utc)


def _obj(key: str, size: int = 10, etag: str = "etag") -> dict[str, Any]:
    return {"key": key, "size": size, "etag": etag}


def _docs(prefix: str, count: int) -> list[dict[str, Any]]:
    return [_obj(f"{prefix}book-{index}.pdf", etag=f"e{index}") for index in range(count)]


class _Store:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}

    def get(self, pk: str, sk: str) -> dict[str, Any] | None:
        item = self.items.get((pk, sk))
        return dict(item) if item else None

    def put(self, item: dict[str, Any]) -> None:
        self.items[(item["pk"], item["sk"])] = dict(item)


class _Agent:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.jobs: dict[str, dict[str, Any]] = {}
        self.documents: list[dict[str, Any]] = []
        self.conflict = False

    def start_ingestion_job(self, **kwargs: Any) -> dict[str, Any]:
        if self.conflict:
            from botocore.exceptions import ClientError

            self.conflict = False
            raise ClientError({"Error": {"Code": "ConflictException", "Message": "running"}}, "StartIngestionJob")
        job_id = f"job-{len(self.started) + 1}"
        self.started.append(kwargs)
        self.jobs[job_id] = {
            "status": "COMPLETE",
            "statistics": {"numberOfDocumentsScanned": 1, "numberOfDocumentsDeleted": 0},
        }
        return {"ingestionJob": {"ingestionJobId": job_id, "status": "STARTING"}}

    def get_ingestion_job(self, **kwargs: Any) -> dict[str, Any]:
        job = self.jobs[kwargs["ingestionJobId"]]
        return {"ingestionJob": {"ingestionJobId": kwargs["ingestionJobId"], **job}}

    def list_ingestion_jobs(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "ingestionJobSummaries": [
                {"ingestionJobId": "adopted", "status": "IN_PROGRESS", "dataSourceId": "ds-theory"}
            ]
        }

    def list_knowledge_base_documents(self, **_kwargs: Any) -> dict[str, Any]:
        return {"documentDetails": self.documents}


class KbSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _Store()
        self.agent = _Agent()
        self.env = patch.dict(
            os.environ,
            {
                "KB_BUCKET_NAME": "kb-bucket",
                "KNOWLEDGE_BASE_ID": "KBID123456",
                "KB_DATA_SOURCE_IDS": json.dumps(
                    {"theory/": "ds-theory", "formula-notes/": "ds-notes", "journal/": "ds-journal"}
                ),
                "KB_MAX_RAW_BYTES": "1000",
            },
        )
        self.env.start()
        self.patches = [
            patch("kb_sync.store.get", self.store.get),
            patch("kb_sync.store.put", self.store.put),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in self.patches:
            item.stop()
        self.env.stop()

    def _run(self, event: dict[str, Any], objects: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        def loader() -> list[dict[str, Any]]:
            if objects is None:
                raise AssertionError("the bucket was listed")
            return objects

        return kb_sync.run(event, loader=loader, agent=self.agent, clock=lambda: NOW)

    def test_the_hash_ignores_listing_order(self) -> None:
        first = kb_sync.manifest([_obj("theory/b.pdf", 2, "e2"), _obj("theory/a.pdf", 1, "e1")])
        second = kb_sync.manifest([_obj("theory/a.pdf", 1, "e1"), _obj("theory/b.pdf", 2, "e2")])
        self.assertEqual(kb_sync.fingerprint(first), kb_sync.fingerprint(second))

    def test_a_sidecar_change_counts_as_a_change(self) -> None:
        base = [_obj("theory/a.pdf"), _obj("theory/a.pdf.metadata.json", 4, "side")]
        changed = [_obj("theory/a.pdf"), _obj("theory/a.pdf.metadata.json", 4, "edited")]
        state = kb_sync.snapshot(kb_sync.manifest(base))
        choice = kb_sync.decide(kb_sync.manifest(changed), state, cap=1000)
        self.assertEqual(choice["status"], "start")
        self.assertEqual(choice["prefixes"], ["theory/"])

    def test_the_schedule_does_not_start_the_first_sync(self) -> None:
        result = self._run({"job": "kb_sync_check"})
        self.assertEqual(result["status"], "awaiting_first_sync")
        self.assertTrue(result["ok"])
        self.assertEqual(self.agent.started, [])
        self.assertEqual(self.store.items, {})

    def test_run_now_starts_one_job_per_changed_prefix(self) -> None:
        result = self._run({"job": "kb_sync_check", "trigger": "manual"}, _docs("theory/", 2))
        self.assertEqual(result["status"], "running")
        self.assertEqual(
            [item["dataSourceId"] for item in self.agent.started],
            ["ds-theory", "ds-notes", "ds-journal"],
        )
        job = self.store.get("JOB#kb_sync_check", "STATE") or {}
        self.assertEqual(job["status"], "running")
        self.assertEqual(job["gsi1pk"], "JOBSTATE")
        self.assertLess(job["leaseUntil"], "2026-11-18T02:30:00.000Z")

    def test_an_unchanged_manifest_starts_nothing(self) -> None:
        objects = _docs("theory/", 2)
        self.store.put({"pk": "KB#state", "sk": "META", **kb_sync.snapshot(kb_sync.manifest(objects))})
        result = self._run({"trigger": "manual"}, objects)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(self.agent.started, [])

    def test_size_and_problems_block_before_a_job_starts(self) -> None:
        oversized = self._run({"trigger": "manual"}, [_obj("theory/big.pdf", 1001)])
        self.assertEqual(oversized["status"], "blocked_size")
        bad = kb_sync.problems(kb_sync.manifest([_obj("theory/notes.markdown")]))
        self.assertEqual(bad, [{"key": "theory/notes.markdown", "problem": "unsupported"}])
        orphan = kb_sync.problems(kb_sync.manifest([_obj("theory/gone.pdf.metadata.json", 11)]))
        self.assertEqual(orphan[0]["problem"], "orphan_sidecar")
        huge = kb_sync.problems(kb_sync.manifest([_obj("theory/a.pdf.metadata.json", 10 * 1024 + 1)]))
        self.assertEqual(huge[0]["problem"], "sidecar_too_large")
        exact = kb_sync.problems(
            kb_sync.manifest([_obj("theory/a.pdf", 50_000_000), _obj("theory/a.pdf.metadata.json", 10 * 1024)])
        )
        self.assertEqual(exact, [])
        self.assertEqual(self.agent.started, [])

    def test_deletion_is_checked_per_prefix_and_confirmation_allows_it(self) -> None:
        previous = _docs("theory/", 100) + _docs("journal/", 10)
        state = kb_sync.snapshot(kb_sync.manifest(previous))
        kept = _docs("theory/", 84) + _docs("journal/", 10)
        blocked = kb_sync.decide(kb_sync.manifest(kept), state, cap=1000)
        self.assertEqual(blocked["status"], "blocked_deletion")
        self.assertEqual([item["prefix"] for item in blocked["deletions"]], ["theory/"])
        boundary = kb_sync.decide(kb_sync.manifest(_docs("theory/", 85) + _docs("journal/", 10)), state, cap=1000)
        self.assertEqual(boundary["status"], "start")
        allowed = kb_sync.decide(kb_sync.manifest(kept), state, confirm=True, cap=1000)
        self.assertEqual(allowed["status"], "start")
        self.assertIn("theory/", allowed["prefixes"])

    def test_a_running_job_is_adopted_when_the_service_reports_a_conflict(self) -> None:
        self.agent.conflict = True
        result = self._run({"trigger": "manual"}, _docs("theory/", 1))
        self.assertEqual(result["status"], "running")
        saved = self.store.get("KB#state", "META") or {}
        self.assertEqual(saved["jobs"]["theory/"], "adopted")

    def test_a_finished_job_stores_the_hash_and_failed_keys(self) -> None:
        objects = [_obj("theory/a.pdf"), _obj("theory/b.pdf")]
        built = kb_sync.manifest(objects)
        self.store.put(
            {
                "pk": "KB#state",
                "sk": "META",
                "jobs": {"theory/": "job-1"},
                "pending": kb_sync.snapshot(built),
                "expectedDeletions": {"theory/": 2},
            }
        )
        self.agent.jobs["job-1"] = {
            "status": "COMPLETE",
            "statistics": {
                "numberOfDocumentsScanned": 1,
                "numberOfDocumentsDeleted": 0,
                "numberOfDocumentsFailed": 1,
            },
        }
        self.agent.documents = [
            {
                "status": "FAILED",
                "identifier": {"s3": {"uri": "s3://kb-bucket/theory/b.pdf"}},
                "statusReason": "unreadable",
            },
            {"status": "INDEXED", "identifier": {"s3": {"uri": "s3://kb-bucket/theory/a.pdf"}}},
        ]
        result = self._run({})
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["failedKeys"], ["theory/b.pdf"])
        self.assertEqual(result["deletionShortfall"]["theory/"], 2)
        saved = self.store.get("KB#state", "META") or {}
        self.assertEqual(saved["manifestHash"], kb_sync.fingerprint(built))
        self.assertNotIn("jobs", saved)
        self.assertEqual((self.store.get("JOB#kb_sync_check", "STATE") or {})["status"], "done")

    def test_an_ingestion_still_in_progress_stays_running(self) -> None:
        self.store.put({"pk": "KB#state", "sk": "META", "jobs": {"theory/": "job-1"}})
        self.agent.jobs["job-1"] = {"status": "IN_PROGRESS", "statistics": {}}
        result = self._run({})
        self.assertEqual(result["status"], "running")
        self.assertIn("jobs", self.store.get("KB#state", "META") or {})
