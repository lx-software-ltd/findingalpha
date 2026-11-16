"""Key routes: scope, write reasons, and the dashboard boundary."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import api_handler


def _event(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    key: dict[str, Any] | None = None,
    admin: bool = False,
) -> dict[str, Any]:
    authorizer: dict[str, Any] = {}
    if admin:
        authorizer["jwt"] = {"claims": {"sub": "user-1", "email": "owner@example.com", "cognito:groups": "[admin]"}}
    if key is not None:
        authorizer["lambda"] = key
    event: dict[str, Any] = {
        "requestContext": {"http": {"method": method, "path": path}, "authorizer": authorizer, "requestId": "req-1"}
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _key(**overrides: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "keyId": "abc123",
        "label": "monitor",
        "tier": "admin",
        "scopes": "system,research,portfolio,operate",
        "write": "1",
    }
    context.update(overrides)
    return context


class _Store:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}

    def get(self, pk: str, sk: str) -> dict[str, Any] | None:
        return self.rows.get((pk, sk))

    def put(self, item: dict[str, Any]) -> None:
        self.rows[(item["pk"], item["sk"])] = dict(item)

    def query_gsi1(self, gsi1pk: str, prefix: str = "") -> list[dict[str, Any]]:
        return [
            item
            for item in self.rows.values()
            if item.get("gsi1pk") == gsi1pk and str(item.get("gsi1sk") or "").startswith(prefix)
        ]


# A route added without an entry here has not decided whether a key may call it.
DECISIONS = {
    ("GET", "/health"): None,
    ("GET", "/me"): None,
    ("GET", "/owner-tasks"): "system",
    ("PUT", "/owner-tasks/"): None,
    ("GET", "/settings"): "system",
    ("PUT", "/settings"): "operate",
    ("GET", "/jobs/runs"): "system",
    ("POST", "/jobs/"): "operate",
    ("GET", "/universe/latest"): "research",
    ("GET", "/system/status"): "system",
    ("GET", "/api-keys"): None,
    ("GET", "/methodology"): "research",
    ("GET", "/screens/latest"): "research",
    ("GET", "/screens/"): "research",
    ("GET", "/backtests"): "research",
    ("GET", "/backtests/"): "research",
}


class PublicApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _Store()
        self.audit = patch("audit.write").start()
        patch("store.get", self.store.get).start()
        patch("store.put", self.store.put).start()
        patch("store.query_gsi1", self.store.query_gsi1).start()
        self.writes = patch.dict("os.environ", {"PUBLIC_API_WRITES_ENABLED": "true"}).start()

    def tearDown(self) -> None:
        patch.stopall()

    def test_every_route_has_a_key_decision(self) -> None:
        seen = set()
        for route in api_handler.ROUTES:
            key = (route.method, route.pattern)
            self.assertIn(key, DECISIONS)
            self.assertEqual(route.key_scope, DECISIONS[key])
            if route.key_scope == "operate":
                self.assertTrue(route.key_write)
            if route.method in {"PUT", "POST", "DELETE"} and route.key_scope is not None:
                self.assertTrue(route.key_write)
            seen.add(key)
        self.assertEqual(seen, set(DECISIONS))

    def test_a_key_without_the_scope_gets_404(self) -> None:
        event = _event("GET", "/public/system/status", key=_key(scopes="research", write="0"))
        response = api_handler.lambda_handler(event, None)
        self.assertEqual(response["statusCode"], 404)

    def test_each_write_reason(self) -> None:
        body = {"ingestEnabled": False}
        cases = [
            (_key(scopes="system", write="1"), "scope"),
            (_key(write="1"), "writes_disabled"),
            (_key(write="0"), "key_read_only"),
            (_key(), "owner_only"),
        ]
        with patch.dict("os.environ", {"PUBLIC_API_WRITES_ENABLED": "false"}):
            response = api_handler.lambda_handler(_event("PUT", "/public/settings", body, key=cases[1][0]), None)
            self.assertEqual(json.loads(response["body"])["reason"], "writes_disabled")
        response = api_handler.lambda_handler(_event("PUT", "/public/settings", body, key=cases[0][0]), None)
        self.assertEqual(json.loads(response["body"])["reason"], "scope")
        response = api_handler.lambda_handler(_event("PUT", "/public/settings", body, key=cases[2][0]), None)
        self.assertEqual(json.loads(response["body"])["reason"], "key_read_only")
        response = api_handler.lambda_handler(
            _event("PUT", "/public/settings", {"ingestEnabled": True}, key=_key()), None
        )
        self.assertEqual(response["statusCode"], 403)
        self.assertEqual(json.loads(response["body"])["reason"], "owner_only")
        self.assertEqual(self.store.rows, {})

    def test_a_key_can_turn_a_switch_off_and_the_audit_actor_is_the_key(self) -> None:
        response = api_handler.lambda_handler(
            _event("PUT", "/public/settings", {"ingestEnabled": False}, key=_key()), None
        )
        self.assertEqual(response["statusCode"], 200)
        self.assertFalse(json.loads(response["body"])["ingestEnabled"])
        self.assertEqual(self.audit.call_args.args[0], "apikey:abc123")

    def test_a_key_on_a_dashboard_path_is_ignored(self) -> None:
        response = api_handler.lambda_handler(_event("GET", "/system/status", key=_key()), None)
        self.assertEqual(response["statusCode"], 403)

    def test_a_dashboard_token_on_a_public_path_is_refused(self) -> None:
        response = api_handler.lambda_handler(_event("GET", "/public/system/status", admin=True), None)
        self.assertEqual(response["statusCode"], 401)

    def test_the_index_lists_only_what_the_key_may_call(self) -> None:
        response = api_handler.lambda_handler(_event("GET", "/public", key=_key(scopes="system", write="0")), None)
        body = json.loads(response["body"])
        paths = {(row["method"], row["path"]) for row in body["routes"]}
        self.assertIn(("GET", "/public/system/status"), paths)
        self.assertNotIn(("GET", "/public/api-keys"), paths)
        self.assertNotIn(("PUT", "/public/settings"), paths)
        self.assertNotIn(("GET", "/public/me"), paths)
        self.assertTrue(all(row["scope"] == "system" for row in body["routes"]))

    def test_the_key_list_never_returns_the_digest(self) -> None:
        self.store.put(
            {
                "pk": "APIKEY#digestvalue",
                "sk": "META",
                "keyId": "abc123",
                "label": "monitor",
                "tier": "admin",
                "scopes": ["system"],
                "allowWrite": False,
                "revoked": False,
                "createdAt": "2026-01-01T00:00:00+00:00",
                "gsi1pk": "APIKEYS",
                "gsi1sk": "2026-01-01T00:00:00+00:00#abc123",
            }
        )
        self.store.put({"pk": "APIKEY#hidden", "sk": "META", "keyId": "hidden", "label": "not indexed"})
        response = api_handler.lambda_handler(_event("GET", "/api-keys", admin=True), None)
        text = response["body"]
        body = json.loads(text)
        self.assertNotIn("APIKEY#", text)
        self.assertNotIn("digestvalue", text)
        self.assertEqual([row["keyId"] for row in body["keys"]], ["abc123"])
        self.assertTrue(body["writesEnabled"])

    def test_an_unmirrored_write_is_forbidden_and_a_read_is_not_found(self) -> None:
        denied = api_handler.lambda_handler(_event("PUT", "/public/owner-tasks/O04", {"done": True}, key=_key()), None)
        self.assertEqual(json.loads(denied["body"])["reason"], "not_mirrored")
        missing = api_handler.lambda_handler(_event("GET", "/public/me", key=_key()), None)
        self.assertEqual(missing["statusCode"], 404)

    def test_a_write_without_the_write_flag_is_owner_only(self) -> None:
        from public_api import deny_reason
        from router import Route

        route = Route("POST", "/jobs/tick/run", lambda _event: None, "jwt", key_scope="system")
        self.assertEqual(deny_reason("POST", route, _key(scopes="system", write="1"), {}), "owner_only")
        self.assertEqual(deny_reason("POST", route, _key(scopes="research", write="1"), {}), "scope")
        self.assertIsNone(deny_reason("GET", route, _key(scopes="system", write="0"), {}))

    def test_a_dashboard_settings_write_keeps_the_bare_subject(self) -> None:
        response = api_handler.lambda_handler(_event("PUT", "/settings", {"ingestEnabled": False}, admin=True), None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(self.audit.call_args.args[0], "user-1")

    def test_key_run_matches_the_jobs_the_panel_can_start(self) -> None:
        payload = json.loads((Path(__file__).resolve().parents[3] / "contracts" / "jobs.json").read_text())
        runnable = {job["name"] for job in payload["jobs"] if job["keyRun"]}
        self.assertEqual(
            runnable,
            {"tick", "ingest_daily", "backfill_prices", "backfill_fundamentals"},
        )
        blocked = {
            "weekly_refresh",
            "broker_setup",
            "broker_smoke",
            "breaker_drill",
            "record_drill",
            "execute_holds",
            "screen",
        }
        for job in payload["jobs"]:
            if job["name"] in blocked:
                self.assertFalse(job["keyRun"])

    def test_a_key_can_start_the_same_ingest_jobs_as_the_panel(self) -> None:
        sent: list[str] = []

        def invoke(name: str, _sub: str) -> None:
            sent.append(name)

        with patch.object(api_handler, "_invoke_engine", invoke), patch("audit.write") as audit:
            prices = api_handler.lambda_handler(_event("POST", "/public/jobs/backfill_prices/run", key=_key()), None)
            weekly = api_handler.lambda_handler(_event("POST", "/public/jobs/weekly_refresh/run", key=_key()), None)
            panel = api_handler.lambda_handler(_event("POST", "/jobs/weekly_refresh/run", admin=True), None)
            daily = api_handler.lambda_handler(_event("POST", "/public/jobs/ingest_daily/run", key=_key()), None)
            facts = api_handler.lambda_handler(
                _event("POST", "/public/jobs/backfill_fundamentals/run", key=_key()), None
            )
            screen = api_handler.lambda_handler(_event("POST", "/public/jobs/screen/run", key=_key()), None)
            drill = api_handler.lambda_handler(_event("POST", "/public/jobs/breaker_drill/run", key=_key()), None)
        self.assertEqual(prices["statusCode"], 202)
        self.assertEqual(weekly["statusCode"], 404)
        self.assertEqual(panel["statusCode"], 202)
        self.assertEqual(daily["statusCode"], 202)
        self.assertEqual(facts["statusCode"], 202)
        self.assertEqual(screen["statusCode"], 404)
        self.assertEqual(drill["statusCode"], 404)
        self.assertEqual(sent, ["backfill_prices", "weekly_refresh", "ingest_daily", "backfill_fundamentals"])
        actors = [call.args[0] for call in audit.call_args_list]
        self.assertIn("user-1", actors)
        self.assertEqual(audit.call_args.args[0], "apikey:abc123")

    def test_a_key_does_not_restart_a_finished_backfill(self) -> None:
        self.store.put({"pk": "JOB#backfill_prices", "sk": "STATE", "status": "done", "cursor": 131, "total": 131})
        sent: list[str] = []
        with patch.object(api_handler, "_invoke_engine", lambda name, _sub: sent.append(name)):
            refused = api_handler.lambda_handler(_event("POST", "/public/jobs/backfill_prices/run", key=_key()), None)
            allowed = api_handler.lambda_handler(_event("POST", "/jobs/backfill_prices/run", admin=True), None)
        self.assertEqual(refused["statusCode"], 409)
        self.assertEqual(json.loads(refused["body"])["message"], "backfill_prices already finished")
        self.assertEqual(allowed["statusCode"], 202)
        self.assertEqual(sent, ["backfill_prices"])


if __name__ == "__main__":
    unittest.main()
