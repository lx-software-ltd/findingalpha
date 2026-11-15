"""Secret reads stay out of the log and out of a long cache."""

from __future__ import annotations

import unittest

import secrets_read


class _Client:
    def __init__(self, payload: str, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail
        self.calls = 0

    def get_secret_value(self, SecretId: str) -> dict[str, str]:
        del SecretId
        self.calls += 1
        if self.fail:
            raise RuntimeError("missing")
        return {"SecretString": self.payload}


class SecretsReadTest(unittest.TestCase):
    def setUp(self) -> None:
        secrets_read.clear_cache()

    def test_returns_the_payload_and_caches_it(self) -> None:
        client = _Client('{"keyId":"k","secret":"super-secret-value"}')
        clock = {"t": 0.0}
        first = secrets_read.read_json_secret(
            "findingalpha/alpaca-paper", ("keyId", "secret"), client=client, now=lambda: clock["t"]
        )
        second = secrets_read.read_json_secret(
            "findingalpha/alpaca-paper", ("keyId", "secret"), client=client, now=lambda: clock["t"]
        )
        self.assertEqual(first["secret"], "super-secret-value")
        self.assertEqual(second, first)
        self.assertEqual(client.calls, 1)

    def test_reloads_after_five_minutes(self) -> None:
        client = _Client('{"token":"one"}')
        clock = {"t": 0.0}
        secrets_read.read_json_secret("findingalpha/openrouter", ("token",), client=client, now=lambda: clock["t"])
        clock["t"] = 300
        secrets_read.read_json_secret("findingalpha/openrouter", ("token",), client=client, now=lambda: clock["t"])
        self.assertEqual(client.calls, 2)

    def test_a_missing_key_names_the_secret_and_is_not_cached(self) -> None:
        client = _Client('{"secret":"super-secret-value"}')
        with self.assertRaises(secrets_read.NotConfigured) as raised:
            secrets_read.read_json_secret("findingalpha/alpaca-paper", ("keyId",), client=client, now=lambda: 0.0)
        self.assertEqual(str(raised.exception), "findingalpha/alpaca-paper")
        self.assertNotIn("super-secret-value", str(raised.exception))
        client.payload = '{"keyId":"k"}'
        secrets_read.read_json_secret("findingalpha/alpaca-paper", ("keyId",), client=client, now=lambda: 0.0)
        self.assertEqual(client.calls, 2)

    def test_a_new_required_key_reads_the_secret_again(self) -> None:
        client = _Client('{"keyId":"k"}')
        secrets_read.read_json_secret("findingalpha/alpaca-paper", ("keyId",), client=client, now=lambda: 0.0)
        client.payload = '{"keyId":"k","secret":"super-secret-value"}'
        payload = secrets_read.read_json_secret(
            "findingalpha/alpaca-paper",
            ("keyId", "secret"),
            client=client,
            now=lambda: 1.0,
        )
        self.assertEqual(payload["secret"], "super-secret-value")
        self.assertEqual(client.calls, 2)
        secrets_read.read_json_secret("findingalpha/alpaca-paper", ("keyId",), client=client, now=lambda: 2.0)
        self.assertEqual(client.calls, 2)

    def test_a_failed_read_is_not_cached(self) -> None:
        client = _Client("{}", fail=True)
        with self.assertRaises(secrets_read.NotConfigured) as raised:
            secrets_read.read_json_secret("findingalpha/alpaca-paper", ("keyId",), client=client, now=lambda: 0.0)
        self.assertIsNone(raised.exception.__cause__)
        client.fail = False
        client.payload = '{"keyId":"k"}'
        secrets_read.read_json_secret("findingalpha/alpaca-paper", ("keyId",), client=client, now=lambda: 0.0)
        self.assertEqual(client.calls, 2)


if __name__ == "__main__":
    unittest.main()
