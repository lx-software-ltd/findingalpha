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

    def test_a_backtest_body_and_its_error_convert(self) -> None:
        payload = {
            "periods": [{"month": "2024-01", "spyGross": 0.1, "spyNet": 0.2, "strategy": 0.3}],
            "labels": ["start", "2024-01"],
            "curves": {"strategy": [1.0], "spyGross": [1.1], "spyNet": [1.2], "cash": [1.0]},
            "lastPriceCount": 4,
            "unpricedCount": 0,
            "missingBenchmarkCount": 1,
            "metrics": {"maxDrawdown": {"drawdown": -0.1, "start": "2020-01", "end": "2020-06"}, "hitRate": 0.5},
        }
        with (
            patch("store.get", return_value={"portfolioSize": 15}),
            patch("research_api.config.data_bucket_name", return_value="data"),
            patch("research_api.s3io.exists", return_value=True),
            patch("research_api.s3io.get_json", return_value=payload),
        ):
            raw = http_call(_event("GET", "/v1/admin/backtests/run-1"), None, raw=True)
        body = json.loads(raw["body"])
        self.assertEqual(body["run_id"], "run-1")
        self.assertEqual(body["portfolio_size"], 15)
        self.assertEqual(body["last_price_count"], 4)
        self.assertEqual(body["periods"][0]["spy_gross"], 0.1)
        self.assertEqual(body["curves"]["spy_gross"], [1.1])
        self.assertNotIn("spyGross", body["curves"])
        self.assertEqual(body["metrics"]["max_drawdown"]["drawdown"], -0.1)
        self.assertNotIn("maxDrawdown", body["metrics"])
        contract = wire_format.load_contract()
        back = wire_format.from_wire(body, contract, "GET /v1/admin/backtests/run-1")
        self.assertEqual(back["runId"], "run-1")
        self.assertEqual(back["curves"]["spyGross"], [1.1])
        self.assertNotIn("spy_gross", back["curves"])

        with patch("store.get", return_value=None):
            error = http_call(_event("GET", "/v1/admin/backtests/missing"), None, raw=True)
        err = json.loads(error["body"])
        self.assertEqual(error["statusCode"], 404)
        self.assertEqual(err["request_id"], "req-wire")
        self.assertEqual(err["message"], "Not found")
        self.assertNotIn("requestId", err)

    def test_universe_screen_and_owner_task_maps_keep_data_keys(self) -> None:
        contract = wire_format.load_contract()
        universe = {
            "gsi1sk": "2024-06-03",
            "asOf": "2024-06-03",
            "members": 4,
            "counts": {"marketCap": 4},
            "sectors": {"consumer_discretionary": 2, "Technology": 1},
            "shareSources": {"cover_classes": 3, "600519.SH": 1},
            "lastPriceDate": "2024-06-03",
        }
        with patch("store.query_gsi1", return_value=[universe]), patch("store.get", return_value=None):
            raw = http_call(_event("GET", "/v1/admin/universe/latest"), None, raw=True)
        body = json.loads(raw["body"])
        self.assertEqual(body["last_price_date"], "2024-06-03")
        self.assertNotIn("lastPriceDate", body)
        self.assertEqual(body["sectors"]["consumer_discretionary"], 2)
        self.assertEqual(body["share_sources"]["cover_classes"], 3)
        self.assertEqual(body["share_sources"]["600519.SH"], 1)
        back = wire_format.from_wire(body, contract, "GET /v1/admin/universe/latest")
        self.assertEqual(back["sectors"]["consumer_discretionary"], 2)
        self.assertEqual(back["shareSources"]["cover_classes"], 3)
        self.assertNotIn("coverClasses", back["shareSources"])

        meta = {
            "asOf": "2017-02-28",
            "gsi1sk": "2017-02-28",
            "registerHash": "abc",
            "shortlistSize": 1,
            "counts": {"shortlisted": 1},
        }
        rows = [
            {
                "rank": 1,
                "symbol": "AAA",
                "groups": {"grossProfitability": 0.2, "fcf_margin": 0.1},
                "factors": {"grossProfitability": 0.4},
                "z": {"net_debt_to_ebitda": 0.3},
            }
        ]
        with (
            patch("store.query_gsi1_latest", return_value=[meta]),
            patch("store.get", return_value=meta),
            patch("research_api.config.data_bucket_name", return_value="data"),
            patch("research_api.s3io.exists", return_value=True),
            patch("research_api.s3io.get_jsonl_gz", return_value=iter(rows)),
        ):
            raw = http_call(_event("GET", "/v1/admin/screens/latest"), None, raw=True)
        screen = json.loads(raw["body"])["rows"][0]
        self.assertEqual(screen["groups"]["grossProfitability"], 0.2)
        self.assertEqual(screen["groups"]["fcf_margin"], 0.1)
        self.assertEqual(screen["factors"]["grossProfitability"], 0.4)
        self.assertEqual(screen["z"]["net_debt_to_ebitda"], 0.3)
        restored = wire_format.from_wire(json.loads(raw["body"]), contract, "GET /v1/admin/screens/latest")
        self.assertEqual(restored["rows"][0]["groups"]["fcf_margin"], 0.1)
        self.assertNotIn("fcfMargin", restored["rows"][0]["groups"])

        stored = [
            {"pk": "OWNER_TASK#O04", "at": "2024-01-15T00:00:00Z"},
            {"pk": "OWNER_TASK#task_extra", "at": "2024-02-01T00:00:00Z"},
        ]
        with patch("store.scan_pk_prefix", return_value=stored):
            raw = http_call(_event("GET", "/v1/admin/owner-tasks"), None, raw=True)
        done = json.loads(raw["body"])["done"]
        self.assertEqual(done["O04"]["at"], "2024-01-15T00:00:00Z")
        self.assertIn("task_extra", done)
        tasks = wire_format.from_wire(json.loads(raw["body"]), contract, "GET /v1/admin/owner-tasks")
        self.assertIn("task_extra", tasks["done"])
        self.assertNotIn("taskExtra", tasks["done"])


if __name__ == "__main__":
    unittest.main()
