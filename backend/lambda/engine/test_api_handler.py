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


if __name__ == "__main__":
    unittest.main()
