"""Knowledge base sync decisions, with a stubbed Bedrock client."""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from typing import Any, Protocol
from unittest.mock import patch

import kb_sync

NOW = datetime(2026, 11, 18, 2, 30, tzinfo=timezone.utc)


class _Patch(Protocol):
    def start(self) -> Any: ...

    def stop(self) -> None: ...


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
        self.stopped: list[str] = []
        self.jobs: dict[str, dict[str, Any]] = {}
        self.documents: list[dict[str, Any]] = []
        self.document_pages: list[dict[str, Any]] | None = None
        self.conflict = False
        self.adopt = True
        self.fail_on = ""

    def start_ingestion_job(self, **kwargs: Any) -> dict[str, Any]:
        from botocore.exceptions import ClientError

        self.started.append(kwargs)
        if kwargs.get("dataSourceId") == self.fail_on:
            raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow"}}, "StartIngestionJob")
        if self.conflict:
            self.conflict = False
            raise ClientError({"Error": {"Code": "ConflictException", "Message": "running"}}, "StartIngestionJob")
        job_id = f"job-{len(self.jobs) + 1}"
        self.jobs[job_id] = {
            "status": "COMPLETE",
            "statistics": {"numberOfDocumentsScanned": 1, "numberOfDocumentsDeleted": 0},
        }
        return {"ingestionJob": {"ingestionJobId": job_id, "status": "STARTING"}}

    def get_ingestion_job(self, **kwargs: Any) -> dict[str, Any]:
        job = self.jobs[kwargs["ingestionJobId"]]
        return {"ingestionJob": {"ingestionJobId": kwargs["ingestionJobId"], **job}}

    def list_ingestion_jobs(self, **_kwargs: Any) -> dict[str, Any]:
        if not self.adopt:
            return {"ingestionJobSummaries": []}
        return {
            "ingestionJobSummaries": [
                {"ingestionJobId": "adopted", "status": "IN_PROGRESS", "dataSourceId": "ds-theory"}
            ]
        }

    def list_knowledge_base_documents(self, **kwargs: Any) -> dict[str, Any]:
        if self.document_pages is not None:
            return self.document_pages.pop(0)
        return {"documentDetails": self.documents}

    def stop_ingestion_job(self, **kwargs: Any) -> dict[str, Any]:
        self.stopped.append(kwargs["ingestionJobId"])
        return {}


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
        self.patches: list[_Patch] = [
            patch("kb_sync_jobs.store.get", self.store.get),
            patch("kb_sync_jobs.store.put", self.store.put),
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
        self.assertEqual([item["dataSourceId"] for item in self.agent.started], ["ds-theory"])
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

    def test_size_blocks_and_a_problem_file_is_skipped(self) -> None:
        oversized = self._run({"trigger": "manual"}, [_obj("theory/big.pdf", 1001)])
        self.assertEqual(oversized["status"], "blocked_size")
        self.assertEqual(self.agent.started, [])
        self.assertEqual((self.store.get("KB#state", "META") or {})["blocked"]["status"], "blocked_size")
        bad = kb_sync.problems(kb_sync.manifest([_obj("theory/notes.rtf")]))
        self.assertEqual(bad, [{"key": "theory/notes.rtf", "problem": "unsupported"}])
        for extension in (".markdown", ".htm", ".pptx"):
            self.assertEqual(kb_sync.problems(kb_sync.manifest([_obj(f"theory/notes{extension}")])), [])
        skipped = self._run({"trigger": "manual"}, [_obj("theory/a.pdf"), _obj("theory/notes.rtf")])
        self.assertEqual(skipped["status"], "running")
        self.assertEqual(skipped["problems"], [{"key": "theory/notes.rtf", "problem": "unsupported"}])
        pending = (self.store.get("KB#state", "META") or {})["pending"]
        self.assertNotIn("theory/notes.rtf", pending["sources"]["theory/"]["keys"])
        orphan = kb_sync.problems(kb_sync.manifest([_obj("theory/gone.pdf.metadata.json", 11)]))
        self.assertEqual(orphan[0]["problem"], "orphan_sidecar")
        huge = kb_sync.problems(kb_sync.manifest([_obj("theory/a.pdf.metadata.json", 10 * 1024 + 1)]))
        self.assertEqual(huge[0]["problem"], "sidecar_too_large")
        exact = kb_sync.problems(
            kb_sync.manifest([_obj("theory/a.pdf", 50_000_000), _obj("theory/a.pdf.metadata.json", 10 * 1024)])
        )
        self.assertEqual(exact, [])
        self.assertEqual([item["dataSourceId"] for item in self.agent.started], ["ds-theory"])

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
                "progress": {"scanned": 1, "indexed": 1, "failed": 0},
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
        self.assertNotIn("progress", saved)
        self.assertEqual((self.store.get("JOB#kb_sync_check", "STATE") or {})["status"], "done")

    def test_an_ingestion_still_in_progress_stays_running(self) -> None:
        self.store.put({"pk": "KB#state", "sk": "META", "jobs": {"theory/": "job-1"}})
        self.agent.jobs["job-1"] = {"status": "IN_PROGRESS", "statistics": {}}
        result = self._run({})
        self.assertEqual(result["status"], "running")
        self.assertIn("jobs", self.store.get("KB#state", "META") or {})

    def test_a_running_ingestion_stores_scanned_and_indexed_counts(self) -> None:
        self.store.put(
            {"pk": "KB#state", "sk": "META", "jobs": {"theory/": "job-1", "journal/": "job-2"}}
        )
        self.agent.jobs["job-1"] = {
            "status": "IN_PROGRESS",
            "statistics": {
                "numberOfDocumentsScanned": 10,
                "numberOfNewDocumentsIndexed": 4,
                "numberOfModifiedDocumentsIndexed": 1,
                "numberOfDocumentsFailed": 2,
            },
        }
        self.agent.jobs["job-2"] = {
            "status": "STARTING",
            "statistics": {"numberOfDocumentsScanned": 3, "numberOfNewDocumentsIndexed": 0},
        }
        result = self._run({})
        self.assertEqual(result["status"], "running")
        saved = self.store.get("KB#state", "META") or {}
        self.assertEqual(saved["progress"], {"scanned": 13, "indexed": 5, "failed": 2})

    def test_a_failed_ingestion_can_be_retried_and_the_token_changes(self) -> None:
        objects = _docs("theory/", 2)
        self._run({"trigger": "manual"}, objects)
        first = self.agent.started[0]["clientToken"]
        for job in self.agent.jobs.values():
            job["status"] = "FAILED"
        failed = self._run({})
        self.assertEqual(failed["status"], "failed")
        saved = self.store.get("KB#state", "META") or {}
        self.assertNotIn("jobs", saved)
        self.assertNotIn("manifestHash", saved)
        self.assertTrue(saved["lastJobs"])
        row = self.store.get("JOB#kb_sync_check", "STATE") or {}
        self.assertEqual(row["status"], "failed")
        self.assertNotIn("failures", row)
        again = self._run({"trigger": "manual"}, _docs("theory/", 3))
        self.assertEqual(again["status"], "running")
        self.assertNotEqual(self.agent.started[-1]["clientToken"], first)

    def test_a_completed_folder_is_kept_when_another_fails(self) -> None:
        objects = _docs("theory/", 1) + [_obj("journal/a.md")]
        built = kb_sync.manifest(objects)
        self.store.put(
            {
                "pk": "KB#state",
                "sk": "META",
                "jobs": {"theory/": "job-1", "journal/": "job-2"},
                "pending": kb_sync.snapshot(built),
            }
        )
        self.agent.jobs["job-1"] = {"status": "COMPLETE", "statistics": {"numberOfDocumentsDeleted": 0}}
        self.agent.jobs["job-2"] = {"status": "FAILED", "statistics": {}}
        failed = self._run({})
        self.assertEqual(failed["status"], "failed")
        self.assertIn("journal/ FAILED", failed["error"])
        saved = self.store.get("KB#state", "META") or {}
        self.assertEqual(saved["sources"]["theory/"]["keys"], ["theory/book-0.pdf"])
        self.assertNotIn("journal/", saved["sources"])
        self.assertNotIn("manifestHash", saved)
        self.agent.started.clear()
        self._run({"trigger": "manual"}, objects)
        self.assertEqual([item["dataSourceId"] for item in self.agent.started], ["ds-journal"])

    def test_a_start_that_raises_keeps_the_job_it_already_started(self) -> None:
        from botocore.exceptions import ClientError

        self.agent.fail_on = "ds-theory"
        with self.assertRaises(ClientError):
            self._run({"trigger": "manual"}, _docs("theory/", 1))
        with self.assertRaises(ClientError):
            self._run({"trigger": "manual"}, _docs("theory/", 1))
        self.assertEqual(self.agent.started[0]["clientToken"], self.agent.started[1]["clientToken"])
        self.assertNotIn(("KB#state", "META"), self.store.items)
        self.assertNotIn(("JOB#kb_sync_check", "STATE"), self.store.items)

        self.agent.fail_on = "ds-journal"
        self.agent.started.clear()
        self.agent.jobs.clear()
        objects = _docs("theory/", 1) + [_obj("journal/a.md")]
        result = self._run({"trigger": "manual"}, objects)
        self.assertEqual(result["status"], "running")
        saved = self.store.get("KB#state", "META") or {}
        self.assertEqual(list(saved["jobs"]), ["theory/"])
        done = self._run({})
        self.assertEqual(done["status"], "done")
        self.assertNotIn("manifestHash", self.store.get("KB#state", "META") or {})
        self.agent.fail_on = ""
        self.agent.started.clear()
        self._run({"job": "kb_sync_check"}, objects)
        self.assertEqual([item["dataSourceId"] for item in self.agent.started], ["ds-journal"])

    def test_a_conflict_with_nothing_to_adopt_does_not_leave_a_running_row(self) -> None:
        self.agent.conflict = True
        self.agent.adopt = False
        result = self._run({"trigger": "manual"}, _docs("theory/", 1))
        self.assertEqual(result["error"], "ingestion already running")
        self.assertNotIn(("JOB#kb_sync_check", "STATE"), self.store.items)
        self.assertNotIn("jobs", self.store.get("KB#state", "META") or {})

    def test_a_running_sync_keeps_the_last_manifest(self) -> None:
        previous = [_obj(f"theory/book-{index}.pdf", size=1, etag=f"e{index}") for index in range(100)]
        base = kb_sync.snapshot(kb_sync.manifest(previous))
        self.store.put(
            {"pk": "KB#state", "sk": "META", "status": "done", "syncedAt": "2026-11-17T00:00:00.000Z", **base}
        )
        started = self._run({"job": "kb_sync_check"}, previous + [_obj("theory/new.pdf")])
        self.assertEqual(started["status"], "running")
        during = self.store.get("KB#state", "META") or {}
        self.assertEqual(during["manifestHash"], base["manifestHash"])
        self.assertEqual(during["sources"], base["sources"])
        for job in self.agent.jobs.values():
            job["status"] = "FAILED"
        self._run({})
        after = self.store.get("KB#state", "META") or {}
        self.assertEqual(after["manifestHash"], base["manifestHash"])
        self.assertEqual(after["syncedAt"], "2026-11-17T00:00:00.000Z")
        blocked = self._run({"job": "kb_sync_check"}, _docs("theory/", 10))
        self.assertEqual(blocked["status"], "blocked_deletion")
        self.assertIn("theory/ 90 of 100", blocked["error"])
        self.assertEqual((self.store.get("KB#state", "META") or {})["blocked"]["deletions"][0]["gone"], 90)

    def test_an_empty_prefix_is_not_started_and_a_removed_one_still_blocks(self) -> None:
        choice = kb_sync.decide(kb_sync.manifest(_docs("theory/", 1)), {}, cap=1000)
        self.assertEqual(choice["prefixes"], ["theory/"])
        state = kb_sync.snapshot(kb_sync.manifest(_docs("journal/", 2)))
        blocked = kb_sync.decide(kb_sync.manifest([]), state, cap=1000)
        self.assertEqual(blocked["status"], "blocked_deletion")
        self.assertEqual(blocked["deletions"][0]["prefix"], "journal/")

    def test_the_schedule_starts_a_later_sync(self) -> None:
        objects = _docs("theory/", 2)
        self.store.put({"pk": "KB#state", "sk": "META", **kb_sync.snapshot(kb_sync.manifest(objects))})
        result = self._run({"job": "kb_sync_check"}, objects + [_obj("journal/note.md")])
        self.assertEqual(result["status"], "running")
        self.assertEqual([item["dataSourceId"] for item in self.agent.started], ["ds-journal"])

    def test_an_old_ingestion_is_stopped(self) -> None:
        self.store.put(
            {
                "pk": "KB#state",
                "sk": "META",
                "jobs": {"theory/": "job-1"},
                "jobStartedAt": "2026-11-17T00:00:00.000Z",
                "manifestHash": "kept",
            }
        )
        self.agent.jobs["job-1"] = {"status": "IN_PROGRESS", "statistics": {}}
        result = self._run({})
        self.assertEqual(result["message"], "stopping")
        self.assertEqual(self.agent.stopped, ["job-1"])
        self.assertIn("jobs", self.store.get("KB#state", "META") or {})
        self.agent.jobs["job-1"]["status"] = "STOPPED"
        failed = self._run({})
        self.assertEqual(failed["status"], "failed")
        self.assertEqual((self.store.get("KB#state", "META") or {})["manifestHash"], "kept")

    def test_an_ingestion_under_a_day_is_left_running(self) -> None:
        self.store.put(
            {
                "pk": "KB#state",
                "sk": "META",
                "jobs": {"theory/": "job-1"},
                "jobStartedAt": "2026-11-17T03:00:00.000Z",
            }
        )
        self.agent.jobs["job-1"] = {"status": "IN_PROGRESS", "statistics": {}}
        result = self._run({})
        self.assertEqual(result["message"], "running")
        self.assertEqual(self.agent.stopped, [])

    def test_the_owner_can_stop_and_a_key_cannot_confirm(self) -> None:
        self.store.put({"pk": "KB#state", "sk": "META", "jobs": {"theory/": "job-1"}, "manifestHash": "kept"})
        self.agent.jobs["job-1"] = {"status": "IN_PROGRESS", "statistics": {}}
        stopped = self._run({"trigger": "manual", "by": "user-1", "params": {"stop": True}})
        self.assertEqual(stopped["message"], "stopping")
        refused = self._run({"trigger": "manual", "by": "apikey:abc123", "params": {"confirmDeletion": True}})
        self.assertEqual(refused["error"], "only the owner can confirm a deletion")
        stopped_by_key = self._run({"trigger": "manual", "by": "apikey:abc123", "params": {"stop": True}})
        self.assertEqual(stopped_by_key["error"], "only the owner can stop a sync")

    def test_a_key_cannot_start_the_first_sync(self) -> None:
        result = self._run({"trigger": "manual", "by": "apikey:abc123"}, _docs("theory/", 1))
        self.assertEqual(result["error"], "the owner starts the first sync")
        self.assertEqual(self.agent.started, [])

    def test_failed_documents_are_read_across_pages(self) -> None:
        self.store.put(
            {
                "pk": "KB#state",
                "sk": "META",
                "jobs": {"theory/": "job-1"},
                "pending": kb_sync.snapshot(kb_sync.manifest([])),
            }
        )
        self.agent.jobs["job-1"] = {"status": "COMPLETE", "statistics": {"numberOfDocumentsDeleted": 0}}
        self.agent.document_pages = [
            {
                "documentDetails": [{"status": "FAILED", "identifier": {"s3": {"uri": "s3://kb-bucket/theory/a.pdf"}}}],
                "nextToken": "more",
            },
            {
                "documentDetails": [
                    {"status": "INDEXED", "identifier": {"s3": {"uri": "s3://kb-bucket/theory/b.pdf"}}},
                    {"status": "FAILED", "identifier": {"s3": {"uri": "s3://kb-bucket/theory/c.pdf"}}},
                ]
            },
        ]
        result = self._run({})
        self.assertEqual(result["failedKeys"], ["theory/a.pdf", "theory/c.pdf"])

    def test_the_bucket_listing_follows_pages_and_skips_folders(self) -> None:
        class _Paginator:
            def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
                prefix = kwargs["Prefix"]
                if prefix == "theory/":
                    return [
                        {"Contents": [{"Key": "theory/a.pdf", "Size": 3, "ETag": '"a"'}]},
                        {"Contents": [{"Key": "theory/", "Size": 0, "ETag": '"dir"'}]},
                    ]
                return [{}]

        class _S3:
            def get_paginator(self, _name: str) -> _Paginator:
                return _Paginator()

        with patch("boto3.client", return_value=_S3()):
            listed = kb_sync._load()
        self.assertEqual(listed, [{"key": "theory/a.pdf", "size": 3, "etag": '"a"'}])
