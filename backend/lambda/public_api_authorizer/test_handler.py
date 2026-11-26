"""Authorizer verdicts. boto3 is stubbed before the handler import."""

from __future__ import annotations

import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("RECORDS_TABLE_NAME", "findingalpha-records")

class _Boto3(types.ModuleType):
    resource: MagicMock
    client: MagicMock


boto3 = _Boto3("boto3")
boto3.resource = MagicMock()
boto3.client = MagicMock()
sys.modules["boto3"] = boto3


class ClientError(Exception):
    def __init__(self, response: dict, operation: str) -> None:
        super().__init__(operation)
        self.response = response
        self.operation_name = operation


class _Exceptions(types.ModuleType):
    ClientError: type[ClientError]


class _Botocore(types.ModuleType):
    exceptions: _Exceptions


exceptions = _Exceptions("botocore.exceptions")
exceptions.ClientError = ClientError
botocore = _Botocore("botocore")
botocore.exceptions = exceptions
sys.modules["botocore"] = botocore
sys.modules["botocore.exceptions"] = exceptions

import api_key_scopes
from api_key_hash import hash_api_key
from api_key_scopes import key_allows_write, normalize_scopes
from handler import _is_expired, lambda_handler

_KEY = "fapk_test-key"


def _event(source_ip: str = "203.0.113.10", authorization: str | None = None) -> dict:
    header = f"Bearer {_KEY}" if authorization is None else authorization
    return {
        "headers": {"authorization": header},
        "requestContext": {"requestId": "req-1", "http": {"method": "GET", "sourceIp": source_ip}},
    }


def _valid_item(**extra: object) -> dict:
    item = {
        "pk": f"APIKEY#{hash_api_key(_KEY)}",
        "sk": "META",
        "keyId": "key-1",
        "label": "monitor",
        "tier": "admin",
        "scopes": ["system"],
        "allowWrite": False,
        "revoked": False,
    }
    item.update(extra)
    return item


class AuthorizerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.table = MagicMock()
        boto3.resource.return_value.Table.return_value = self.table
        self.table.get_item.return_value = {"Item": _valid_item()}

    def test_missing_or_blank_or_too_long_key_is_denied(self) -> None:
        for headers in ({}, {"authorization": "   "}, {"authorization": "Bearer " + ("x" * 257)}):
            event = _event()
            event["headers"] = headers
            self.assertFalse(lambda_handler(event, None)["isAuthorized"])
        self.table.get_item.assert_not_called()

    def test_bearer_scheme_is_required_in_any_letter_case(self) -> None:
        self.assertTrue(lambda_handler(_event(authorization=f"bearer {_KEY}"), None)["isAuthorized"])
        self.assertTrue(lambda_handler(_event(authorization=f"BEARER {_KEY}"), None)["isAuthorized"])
        for authorization in (_KEY, f"Token {_KEY}", "Bearer"):
            self.assertFalse(lambda_handler(_event(authorization=authorization), None)["isAuthorized"])
        self.table.get_item.assert_called()

    def test_unknown_key_is_denied(self) -> None:
        self.table.get_item.return_value = {}
        self.assertFalse(lambda_handler(_event(), None)["isAuthorized"])

    def test_admin_key_is_allowed_and_context_has_no_digest(self) -> None:
        out = lambda_handler(_event(), None)
        self.assertTrue(out["isAuthorized"])
        self.assertEqual(out["context"]["tier"], "admin")
        self.assertEqual(out["context"]["scopes"], "system")
        self.assertEqual(out["context"]["write"], "0")
        self.assertNotIn("pk", out["context"])
        self.assertNotIn(hash_api_key(_KEY), str(out))
        self.table.get_item.assert_called_with(Key={"pk": f"APIKEY#{hash_api_key(_KEY)}", "sk": "META"})

    def test_user_tier_is_denied(self) -> None:
        self.table.get_item.return_value = {"Item": _valid_item(tier="user", scopes=["research"], allowWrite=True)}
        self.assertFalse(lambda_handler(_event(), None)["isAuthorized"])

    def test_missing_tier_is_denied(self) -> None:
        item = _valid_item()
        del item["tier"]
        self.table.get_item.return_value = {"Item": item}
        self.assertFalse(lambda_handler(_event(), None)["isAuthorized"])

    def test_scope_outside_the_tier_is_dropped(self) -> None:
        self.table.get_item.return_value = {"Item": _valid_item(scopes=["system", "not-a-scope", "research"])}
        out = lambda_handler(_event(), None)
        self.assertTrue(out["isAuthorized"])
        self.assertEqual(out["context"]["scopes"], "research,system")

    def test_allow_write_on_a_tier_that_may_not_write_is_zero(self) -> None:
        reader = {"enabled": True, "scopes": ("system",), "mayWrite": False}
        with patch.dict(api_key_scopes.TIERS, {"reader": reader}):
            self.table.get_item.return_value = {"Item": _valid_item(tier="reader", scopes=["system"], allowWrite=True)}
            out = lambda_handler(_event(), None)
        self.assertTrue(out["isAuthorized"])
        self.assertEqual(out["context"]["write"], "0")

    def test_method_does_not_change_the_verdict(self) -> None:
        self.table.get_item.return_value = {"Item": _valid_item(scopes=["operate"], allowWrite=True)}
        post = _event()
        post["requestContext"]["http"]["method"] = "POST"
        out = lambda_handler(post, None)
        self.assertTrue(out["isAuthorized"])
        self.assertEqual(out["context"]["write"], "1")

    def test_cidr_blocks_other_ip_and_a_missing_ip(self) -> None:
        self.table.get_item.return_value = {"Item": _valid_item(allowedCidrs=["10.0.0.0/8"])}
        self.assertFalse(lambda_handler(_event(source_ip="203.0.113.10"), None)["isAuthorized"])
        self.assertTrue(lambda_handler(_event(source_ip="10.1.2.3"), None)["isAuthorized"])
        event = _event()
        event["requestContext"]["http"] = {}
        self.assertFalse(lambda_handler(event, None)["isAuthorized"])

    def test_revoked_and_expired_and_garbage_expiry_are_denied(self) -> None:
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        cases: tuple[dict[str, object], ...] = (
            {"revoked": True},
            {"expiresAt": past},
            {"expiresAt": "not-a-date"},
        )
        for extra in cases:
            self.table.get_item.return_value = {"Item": _valid_item(**extra)}
            self.assertFalse(lambda_handler(_event(), None)["isAuthorized"])

    def test_future_expiry_is_allowed(self) -> None:
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        self.table.get_item.return_value = {"Item": _valid_item(expiresAt=future)}
        self.assertTrue(lambda_handler(_event(), None)["isAuthorized"])

    def test_table_error_is_denied(self) -> None:
        self.table.get_item.side_effect = ClientError({"Error": {"Code": "InternalServerError"}}, "GetItem")
        self.assertFalse(lambda_handler(_event(), None)["isAuthorized"])

    def test_last_used_is_throttled_to_sixty_seconds(self) -> None:
        now = datetime(2026, 6, 15, tzinfo=timezone.utc)
        self.table.get_item.return_value = {"Item": _valid_item(lastUsedAt=now.isoformat())}
        with patch("handler.datetime") as clock:
            clock.now.return_value = now + timedelta(seconds=30)
            clock.fromisoformat = datetime.fromisoformat
            lambda_handler(_event(), None)
            self.table.update_item.assert_not_called()
            clock.now.return_value = now + timedelta(seconds=60)
            lambda_handler(_event(), None)
        self.table.update_item.assert_called_once()


class KeyRuleTest(unittest.TestCase):
    def test_write_requires_an_enabled_tier_that_may_write(self) -> None:
        self.assertFalse(key_allows_write({}))
        self.assertFalse(key_allows_write({"tier": "admin", "allowWrite": False}))
        self.assertFalse(key_allows_write({"tier": "user", "allowWrite": True}))
        self.assertTrue(key_allows_write({"tier": "admin", "allowWrite": True}))
        self.assertTrue(key_allows_write({"tier": "admin", "allowWrite": "true"}))

    def test_normalize_drops_scopes_the_tier_does_not_list(self) -> None:
        self.assertEqual(normalize_scopes({"tier": "admin", "scopes": ["system", "nope"]}), ["system"])
        self.assertEqual(normalize_scopes({"tier": "user", "scopes": ["research"]}), [])


class HashTest(unittest.TestCase):
    def test_digest_is_deterministic_hex(self) -> None:
        digest = hash_api_key(_KEY)
        self.assertEqual(digest, hash_api_key(_KEY))
        self.assertEqual(len(digest), 64)
        self.assertNotEqual(hash_api_key("fapk_other"), digest)
        self.assertTrue(all(char in "0123456789abcdef" for char in digest))


class ExpiredTest(unittest.TestCase):
    def test_absent_never_expires_and_garbage_fails_closed(self) -> None:
        now = datetime(2026, 6, 15, tzinfo=timezone.utc)
        self.assertFalse(_is_expired(None, now))
        self.assertFalse(_is_expired("", now))
        self.assertTrue(_is_expired("not-a-date", now))
        self.assertTrue(_is_expired("2026-06-01", now))
        self.assertFalse(_is_expired("2026-07-01", now))
        self.assertTrue(_is_expired("2026-06-01T00:00:00Z", now))


if __name__ == "__main__":
    unittest.main()
