"""Health and me."""

from __future__ import annotations

import json
import unittest

import api_handler
from http_call import http_call


def _event(method: str, path: str, groups: str | None = None) -> dict:
    event: dict = {"requestContext": {"http": {"method": method, "path": path}, "authorizer": {"jwt": {"claims": {}}}}}
    if groups is not None:
        event["requestContext"]["authorizer"]["jwt"]["claims"] = {
            "sub": "user-1",
            "email": "owner@example.com",
            "cognito:groups": groups,
        }
    return event


class ApiHandlerTest(unittest.TestCase):
    def test_health_needs_no_token(self) -> None:
        response = http_call(_event("GET", "/health"), None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"])["status"], "ok")

    def test_me_without_admin_is_forbidden(self) -> None:
        response = http_call(_event("GET", "/v1/admin/me", "[viewer]"), None)
        self.assertEqual(response["statusCode"], 403)

    def test_me_returns_only_the_three_fields(self) -> None:
        response = http_call(_event("GET", "/v1/admin/me", "[admin]"), None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(
            set(json.loads(response["body"])),
            {"sub", "email", "groups"},
        )

    def test_methodology_returns_the_register_and_the_hash(self) -> None:
        response = http_call(_event("GET", "/v1/admin/methodology", "[admin]"), None)
        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(len(body["hash"]), 16)
        self.assertEqual(body["counts"]["provisional"], 0)
        self.assertEqual(body["counts"]["cited"], 1)
        self.assertEqual(body["counts"]["ownerAccepted"], 16)
        self.assertEqual(body["counts"]["entries"], 17)
        self.assertIn("roic", {item["id"] for item in body["register"]["factors"]})

    def test_unknown_path_is_not_found(self) -> None:
        response = http_call(_event("GET", "/v1/admin/missing", "[admin]"), None)
        self.assertEqual(response["statusCode"], 404)

    def test_a_manual_job_is_accepted_and_an_unknown_job_is_not(self) -> None:
        from unittest.mock import patch

        sent: list[tuple[str, str]] = []

        def invoke(name: str, sub: str) -> None:
            sent.append((name, sub))

        with patch.object(api_handler, "_invoke_engine", invoke), patch("audit.write"):
            allowed = http_call(_event("POST", "/v1/admin/jobs/ingest_daily/run", "[admin]"), None)
            missing = http_call(_event("POST", "/v1/admin/jobs/reconcile/run", "[admin]"), None)
        self.assertEqual(allowed["statusCode"], 202)
        self.assertEqual(json.loads(allowed["body"]), {"accepted": True})
        self.assertEqual(sent, [("ingest_daily", "user-1")])
        self.assertEqual(missing["statusCode"], 404)
        plain = http_call(_event("POST", "/v1/admin/jobs/broker_setup/run", "[admin]"), None)
        self.assertEqual(plain["statusCode"], 404)
        self.assertEqual(sent, [("ingest_daily", "user-1")])

    def test_the_knowledge_base_sync_route_starts_the_same_job(self) -> None:
        from unittest.mock import patch

        sent: list[tuple[str, object]] = []

        def invoke(name: str, _sub: str, params: dict | None = None) -> None:
            sent.append((name, params))

        with patch.object(api_handler, "_invoke_engine", invoke), patch("audit.write"):
            started = http_call(_event("POST", "/v1/admin/kb/sync", "[admin]"), None)
            confirmed = _event("POST", "/v1/admin/kb/sync", "[admin]")
            confirmed["body"] = json.dumps({"confirmDeletion": True})
            allowed = http_call(confirmed, None)
        self.assertEqual(started["statusCode"], 202)
        self.assertEqual(allowed["statusCode"], 202)
        self.assertEqual(sent, [("kb_sync_check", None), ("kb_sync_check", {"confirmDeletion": True})])

    def test_a_sync_accepts_only_an_empty_body_or_a_deletion_confirmation(self) -> None:
        from unittest.mock import patch

        sent: list[tuple[str, object]] = []
        audited: list[str] = []

        def invoke(name: str, sub: str, params: dict | None = None) -> None:
            sent.append((name, params))

        def write(_actor: str, _action: str, target: str, _event: dict) -> None:
            audited.append(target)

        with patch.object(api_handler, "_invoke_engine", invoke), patch("audit.write", write):
            empty = http_call(_event("POST", "/v1/admin/jobs/kb_sync_check/run", "[admin]"), None)
            confirmed = _event("POST", "/v1/admin/jobs/kb_sync_check/run", "[admin]")
            confirmed["body"] = json.dumps({"confirmDeletion": True})
            allowed = http_call(confirmed, None)
            rejected = _event("POST", "/v1/admin/jobs/kb_sync_check/run", "[admin]")
            rejected["body"] = json.dumps({"confirmDeletion": False})
            refused = http_call(rejected, None)
            stopped = _event("POST", "/v1/admin/jobs/kb_sync_check/run", "[admin]")
            stopped["body"] = json.dumps({"stop": True})
            halt = http_call(stopped, None)
        self.assertEqual(empty["statusCode"], 202)
        self.assertEqual(allowed["statusCode"], 202)
        self.assertEqual(halt["statusCode"], 202)
        self.assertEqual(
            sent,
            [
                ("kb_sync_check", None),
                ("kb_sync_check", {"confirmDeletion": True}),
                ("kb_sync_check", {"stop": True}),
            ],
        )
        self.assertEqual(audited[-2], "kb_sync_check confirmDeletion")
        self.assertEqual(audited[-1], "kb_sync_check stop")
        self.assertEqual(refused["statusCode"], 400)

    def test_the_latest_universe_is_the_newest_finished_row(self) -> None:
        from unittest.mock import patch

        rows = [
            {"gsi1sk": "2024-06-01", "asOf": "2024-06-01", "members": 2, "counts": {"marketCap": 2}},
            {
                "gsi1sk": "2024-06-03",
                "asOf": "2024-06-03",
                "members": 4,
                "counts": {"marketCap": 4},
                "lastPriceDate": "2024-06-03",
            },
            {"gsi1sk": "2024-06-02", "members": 9},
        ]

        def get(pk: str, _sk: str) -> dict[str, object] | None:
            if pk == "JOB#backfill_prices":
                return {"status": "running", "cursor": 2, "total": 8}
            return None

        with patch("store.query_gsi1", return_value=rows), patch("store.get", side_effect=get):
            response = http_call(_event("GET", "/v1/admin/universe/latest", "[admin]"), None)
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["asOf"], "2024-06-03")
        self.assertEqual(body["lastPriceDate"], "2024-06-03")
        self.assertEqual(body["members"], 4)
        self.assertEqual(body["counts"]["marketCap"], 4)
        self.assertEqual(body["backfill"]["prices"], {"status": "running", "cursor": 2, "total": 8})
        self.assertIsNone(body["backfill"]["fundamentals"])

    def test_an_empty_universe_still_has_backfill_progress(self) -> None:
        from unittest.mock import patch

        with patch("store.query_gsi1", return_value=[]), patch("store.get", return_value=None):
            response = http_call(_event("GET", "/v1/admin/universe/latest", "[admin]"), None)
        body = json.loads(response["body"])
        self.assertEqual(body["asOf"], None)
        self.assertEqual(body["members"], 0)
        self.assertIn("backfill", body)
        self.assertIsNone(body["backfill"]["prices"])


if __name__ == "__main__":
    unittest.main()
