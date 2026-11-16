"""Health and me."""

from __future__ import annotations

import json
import unittest

import api_handler


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
        response = api_handler.lambda_handler(_event("GET", "/health"), None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"])["ok"], True)

    def test_me_without_admin_is_forbidden(self) -> None:
        response = api_handler.lambda_handler(_event("GET", "/me", "[viewer]"), None)
        self.assertEqual(response["statusCode"], 403)

    def test_me_returns_only_the_three_fields(self) -> None:
        response = api_handler.lambda_handler(_event("GET", "/me", "[admin]"), None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(
            set(json.loads(response["body"])),
            {"sub", "email", "groups"},
        )

    def test_unknown_path_is_not_found(self) -> None:
        response = api_handler.lambda_handler(_event("GET", "/missing", "[admin]"), None)
        self.assertEqual(response["statusCode"], 404)

    def test_a_manual_job_is_accepted_and_an_unknown_job_is_not(self) -> None:
        from unittest.mock import patch

        sent: list[tuple[str, str]] = []

        def invoke(name: str, sub: str) -> None:
            sent.append((name, sub))

        with patch.object(api_handler, "_invoke_engine", invoke), patch("audit.write"):
            allowed = api_handler.lambda_handler(_event("POST", "/jobs/ingest_daily/run", "[admin]"), None)
            missing = api_handler.lambda_handler(_event("POST", "/jobs/reconcile/run", "[admin]"), None)
        self.assertEqual(allowed["statusCode"], 202)
        self.assertEqual(json.loads(allowed["body"]), {"accepted": True})
        self.assertEqual(sent, [("ingest_daily", "user-1")])
        self.assertEqual(missing["statusCode"], 404)

    def test_the_latest_universe_is_the_newest_finished_row(self) -> None:
        from unittest.mock import patch

        rows = [
            {"gsi1sk": "2024-06-01", "asOf": "2024-06-01", "members": 2, "counts": {"marketCap": 2}},
            {"gsi1sk": "2024-06-03", "asOf": "2024-06-03", "members": 4, "counts": {"marketCap": 4}},
            {"gsi1sk": "2024-06-02", "members": 9},
        ]
        with patch("store.query_gsi1", return_value=rows):
            response = api_handler.lambda_handler(_event("GET", "/universe/latest", "[admin]"), None)
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["asOf"], "2024-06-03")
        self.assertEqual(body["members"], 4)
        self.assertEqual(body["counts"]["marketCap"], 4)


if __name__ == "__main__":
    unittest.main()
