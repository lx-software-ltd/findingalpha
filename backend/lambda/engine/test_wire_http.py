"""Wire shapes at the HTTP boundary. Handlers keep camelCase."""

from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import patch

import api_handler
import wire_format
from http_call import http_call


def _event(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "requestContext": {
            "http": {"method": method, "path": path},
            "authorizer": {
                "jwt": {"claims": {"sub": "user-1", "email": "owner@example.com", "cognito:groups": "[admin]"}}
            },
            "requestId": "req-wire",
        },
        "headers": {"content-type": "application/json"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


class WireHttpTest(unittest.TestCase):
    def test_a_settings_response_is_snake_case_and_the_handler_keeps_camel_case(self) -> None:
        saved: dict[str, Any] = {}

        def put(row: dict[str, Any]) -> None:
            saved.update(row)

        with patch("store.get", return_value={"ingestEnabled": True}), patch("store.put", put), patch("audit.write"):
            raw = http_call(_event("GET", "/v1/admin/settings"), None, raw=True)
            written = http_call(_event("PUT", "/v1/admin/settings", {"ingestEnabled": False}), None)
        wire = json.loads(raw["body"])
        self.assertEqual(wire["ingest_enabled"], True)
        self.assertNotIn("ingestEnabled", wire)
        self.assertEqual(written["statusCode"], 200)
        self.assertIs(saved["ingestEnabled"], False)
        self.assertIn("ingestEnabled", json.loads(written["body"]))

    def test_an_error_carries_request_id_and_keeps_message(self) -> None:
        response = http_call(_event("GET", "/v1/admin/missing"), None, raw=True)
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 404)
        self.assertEqual(body["code"], "not_found")
        self.assertEqual(body["message"], "Not found")
        self.assertEqual(body["request_id"], "req-wire")
        self.assertNotIn("requestId", body)
        self.assertEqual(response["headers"]["x-request-id"], "req-wire")

    def test_a_job_run_list_is_snake_case(self) -> None:
        rows = [
            {
                "job": "ingest_daily",
                "status": "succeeded",
                "gsi1sk": "2026-11-26T00:00:00Z",
                "sk": "RUN#2026-11-26T00:00:00Z",
                "errorMessage": "",
            }
        ]
        event = _event("GET", "/v1/admin/jobs/runs")
        event["queryStringParameters"] = {"limit": "1", "pageSize": "1"}
        with patch("store.query_gsi1_latest", return_value=rows):
            response = http_call(event, None, raw=True)
        run = json.loads(response["body"])["runs"][0]
        self.assertEqual(run["started_at"], "2026-11-26T00:00:00Z")
        self.assertIn("duration_ms", run)
        self.assertNotIn("startedAt", run)

    def test_query_and_path_names_convert_and_the_handler_reads_camel_case(self) -> None:
        contract = wire_format.load_contract()
        prepared = wire_format.prepare_request(
            {
                "rawPath": "/v1/admin/jobs/wrong/run",
                "headers": {"content-type": "application/json"},
                "queryStringParameters": {"page_size": "10"},
                "pathParameters": {"job_name": "ingest_daily"},
                "body": json.dumps({"ingest_enabled": False}),
                "requestContext": {"http": {"path": "/v1/admin/jobs/wrong/run", "method": "POST"}},
            },
            contract,
        )
        self.assertEqual(prepared["queryStringParameters"], {"pageSize": "10"})
        self.assertEqual(prepared["pathParameters"], {"jobName": "ingest_daily"})
        self.assertEqual(json.loads(prepared["body"]), {"ingestEnabled": False})

        event = _event("POST", "/v1/admin/jobs/wrong/run")
        event["pathParameters"] = {"jobName": "ingest_daily"}
        sent: list[str] = []
        with patch.object(api_handler, "_invoke_engine", lambda name, _sub: sent.append(name)), patch("audit.write"):
            response = http_call(event, None)
        self.assertEqual(response["statusCode"], 202)
        self.assertEqual(sent, ["ingest_daily"])

    def test_methodology_counts_convert_and_the_register_stays(self) -> None:
        response = http_call(_event("GET", "/v1/admin/methodology"), None, raw=True)
        body = json.loads(response["body"])
        self.assertIn("owner_accepted", body["counts"])
        self.assertNotIn("ownerAccepted", body["counts"])
        self.assertIn("roic", {item["id"] for item in body["register"]["factors"]})


if __name__ == "__main__":
    unittest.main()
