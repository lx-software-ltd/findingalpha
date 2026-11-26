"""Dashboard routes: owner tasks, settings, and system status."""

from __future__ import annotations

import json
import os
import unittest
from typing import Any, Protocol
from unittest.mock import patch

from http_call import http_call


class _Patch(Protocol):
    def start(self) -> Any: ...

    def stop(self) -> None: ...


def _event(method: str, path: str, body: dict[str, Any] | None = None, limit: str | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "requestContext": {
            "http": {"method": method, "path": path},
            "authorizer": {
                "jwt": {"claims": {"sub": "user-1", "email": "owner@example.com", "cognito:groups": "[admin]"}}
            },
            "requestId": "req-1",
        }
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if limit is not None:
        event["queryStringParameters"] = {"limit": limit}
    return event


class _Store:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}

    def get(self, pk: str, sk: str) -> dict[str, Any] | None:
        return self.rows.get((pk, sk))

    def put(self, item: dict[str, Any]) -> None:
        self.rows[(item["pk"], item["sk"])] = dict(item)

    def delete(self, pk: str, sk: str) -> None:
        self.rows.pop((pk, sk), None)

    def scan_pk_prefix(self, prefix: str) -> list[dict[str, Any]]:
        return [item for (pk, _sk), item in self.rows.items() if pk.startswith(prefix)]

    def query_latest(self, pk: str, prefix: str, limit: int = 1) -> list[dict[str, Any]]:
        rows = [item for (key, sk), item in self.rows.items() if key == pk and sk.startswith(prefix)]
        rows.sort(key=lambda item: item["sk"], reverse=True)
        return rows[:limit]

    def query_gsi1(self, gsi1pk: str, prefix: str = "") -> list[dict[str, Any]]:
        return [
            item
            for item in self.rows.values()
            if item.get("gsi1pk") == gsi1pk and str(item.get("gsi1sk") or "").startswith(prefix)
        ]

    def query_gsi1_latest(self, gsi1pk: str, limit: int) -> list[dict[str, Any]]:
        rows = [item for item in self.rows.values() if item.get("gsi1pk") == gsi1pk]
        rows.sort(key=lambda item: str(item.get("gsi1sk")), reverse=True)
        return rows[:limit]


class DashboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _Store()
        self.patches: list[_Patch] = [
            patch("store.get", self.store.get),
            patch("store.put", self.store.put),
            patch("store.delete", self.store.delete),
            patch("store.scan_pk_prefix", self.store.scan_pk_prefix),
            patch("store.query_latest", self.store.query_latest),
            patch("store.query_gsi1", self.store.query_gsi1),
            patch("store.query_gsi1_latest", self.store.query_gsi1_latest),
            patch("audit.write"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in self.patches:
            item.stop()

    def test_settings_reject_an_unknown_key_and_keep_booleans(self) -> None:
        denied = http_call(_event("PUT", "/v1/admin/settings", {"ingestEnabled": True, "extra": True}), None)
        self.assertEqual(denied["statusCode"], 400)
        saved = http_call(_event("PUT", "/v1/admin/settings", {"ingestEnabled": True}), None)
        self.assertEqual(json.loads(saved["body"])["ingestEnabled"], True)
        listed = json.loads(http_call(_event("GET", "/v1/admin/settings"), None)["body"])
        self.assertTrue(listed["ingestEnabled"])
        self.assertFalse(listed["tradingEnabled"])

    def test_owner_task_id_must_match_and_a_tick_is_listed(self) -> None:
        bad = http_call(_event("PUT", "/v1/admin/owner-tasks/nope", {"done": True}), None)
        self.assertEqual(bad["statusCode"], 400)
        ok = http_call(_event("PUT", "/v1/admin/owner-tasks/O04", {"done": True}), None)
        self.assertEqual(ok["statusCode"], 200)
        done = json.loads(http_call(_event("GET", "/v1/admin/owner-tasks"), None)["body"])["done"]
        self.assertIn("O04", done)
        http_call(_event("PUT", "/v1/admin/owner-tasks/O04", {"done": False}), None)
        done = json.loads(http_call(_event("GET", "/v1/admin/owner-tasks"), None)["body"])["done"]
        self.assertNotIn("O04", done)

    def test_status_lists_jobs_and_the_latest_run(self) -> None:
        os.environ["INGEST_ENABLED"] = "true"
        self.store.put(
            {
                "pk": "SETTINGS#global",
                "sk": "META",
                "ingestEnabled": True,
            }
        )
        self.store.put(
            {
                "pk": "JOB#tick",
                "sk": "RUN#2026-01-01T00:00:00.000Z",
                "gsi1pk": "JOBRUNS",
                "gsi1sk": "2026-01-01T00:00:00.000Z",
                "job": "tick",
                "status": "succeeded",
                "finishedAt": "2026-01-01T00:00:01.000Z",
            }
        )
        body = json.loads(http_call(_event("GET", "/v1/admin/system/status"), None)["body"])
        ingest = next(item for item in body["switches"] if item["name"] == "ingestEnabled")
        self.assertTrue(ingest["effective"])
        self.assertEqual(body["brokerMode"], "paper")
        tick = next(item for item in body["jobs"] if item["job"] == "tick")
        self.assertEqual(tick["lastRun"]["status"], "succeeded")
        self.assertEqual(tick["schedule"], "rate(15 minutes)")
        self.assertTrue(tick["keyRun"])
        self.assertIsNone(tick["progress"])
        never = next(item for item in body["jobs"] if item["job"] == "ingest_daily")
        self.assertIsNone(never["lastRun"])
        self.assertTrue(never["manualRun"])
        self.assertTrue(never["keyRun"])
        broker = next(item for item in body["jobs"] if item["job"] == "broker_setup")
        self.assertFalse(broker["manualRun"])
        sync = next(item for item in body["jobs"] if item["job"] == "kb_sync_check")
        self.assertTrue(sync["manualRun"])
        self.assertEqual(sync["schedule"], "30 5 * * ? * Asia/Hong_Kong")
        self.assertTrue(broker["keyRun"])
        self.store.put(
            {
                "pk": "JOB#backfill_prices",
                "sk": "STATE",
                "status": "running",
                "cursor": 11,
                "total": 131,
                "gsi1pk": "JOBSTATE",
                "gsi1sk": "backfill_prices",
            }
        )
        again = json.loads(http_call(_event("GET", "/v1/admin/system/status"), None)["body"])
        prices = next(item for item in again["jobs"] if item["job"] == "backfill_prices")
        self.assertEqual(prices["progress"], {"status": "running", "cursor": 11, "total": 131})
        runs = json.loads(http_call(_event("GET", "/v1/admin/jobs/runs", limit="1"), None)["body"])["runs"]
        self.assertEqual(len(runs), 1)
        os.environ.pop("INGEST_ENABLED", None)

    def test_viewer_is_forbidden(self) -> None:
        event = _event("GET", "/v1/admin/settings")
        event["requestContext"]["authorizer"]["jwt"]["claims"]["cognito:groups"] = "[viewer]"
        self.assertEqual(http_call(event, None)["statusCode"], 403)


if __name__ == "__main__":
    unittest.main()
