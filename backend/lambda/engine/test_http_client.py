"""HTTP retries and the rate limiter."""

from __future__ import annotations

import http.client
import io
import json
import logging
import ssl
import unittest
import urllib.error
from email.message import Message
from typing import Literal

import http_client


class _Capture(logging.Handler):
    def __init__(self, records: list[logging.LogRecord]) -> None:
        super().__init__()
        self.records = records

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> Literal[False]:
        return False


def _http_error(status: int, body: bytes, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://example.com/x", status, "err", headers, io.BytesIO(body))


class HttpClientTest(unittest.TestCase):
    def test_get_json_returns_the_body(self) -> None:
        def opener(_request: object, timeout: float) -> _Response:
            self.assertEqual(timeout, 30)
            return _Response(b'{"ok":true}')

        self.assertEqual(http_client.get_json("https://example.com/x", opener=opener), {"ok": True})

    def test_server_error_retries_then_succeeds(self) -> None:
        calls = {"n": 0}
        slept: list[float] = []

        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            calls["n"] += 1
            if calls["n"] < 3:
                raise _http_error(500, b"down")
            return _Response(b"up")

        text = http_client.get_text("https://example.com/x", opener=opener, sleep=slept.append)
        self.assertEqual(text, "up")
        self.assertEqual(slept, [0.5, 1.0])

    def test_retry_after_is_honoured(self) -> None:
        calls = {"n": 0}
        slept: list[float] = []

        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(429, b"slow", retry_after="3")
            return _Response(b"ok")

        http_client.get_text("https://example.com/x", opener=opener, sleep=slept.append)
        self.assertEqual(slept, [3.0])

    def test_a_long_retry_after_is_a_failure(self) -> None:
        calls = {"n": 0}
        slept: list[float] = []

        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            calls["n"] += 1
            raise _http_error(429, b"later", retry_after="30")

        with self.assertRaises(http_client.HttpStatusError) as raised:
            http_client.get_text("https://example.com/x", opener=opener, sleep=slept.append)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(slept, [])
        self.assertEqual(raised.exception.status, 429)

    def test_forbidden_is_not_retried_unless_asked(self) -> None:
        calls = {"n": 0}

        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(403, b"slow", retry_after="0")
            return _Response(b"ok")

        with self.assertRaises(http_client.HttpStatusError):
            http_client.get_text("https://example.com/x", opener=opener, sleep=self.fail)
        self.assertEqual(calls["n"], 1)
        calls["n"] = 0
        text = http_client.get_text(
            "https://example.com/x",
            opener=opener,
            sleep=lambda _seconds: None,
            retry_on=frozenset({403}),
        )
        self.assertEqual(text, "ok")
        self.assertEqual(calls["n"], 2)

    def test_a_stray_byte_can_fall_back_to_latin1(self) -> None:
        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            return _Response(b"caf\xe9")

        with self.assertRaises(UnicodeDecodeError):
            http_client.get_text("https://example.com/x", opener=opener)
        text = http_client.get_text("https://example.com/x", opener=opener, errors="fallback")
        self.assertEqual(text, "café")

    def test_client_error_is_not_retried_and_the_body_is_closed(self) -> None:
        body = io.BytesIO(b"missing")
        headers = Message()

        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            raise urllib.error.HTTPError("https://example.com/x", 404, "missing", headers, body)

        with self.assertRaises(http_client.HttpStatusError) as raised:
            http_client.get_text("https://example.com/x", opener=opener, sleep=self.fail)
        self.assertEqual(raised.exception.status, 404)
        self.assertEqual(raised.exception.body, "missing")
        self.assertTrue(body.closed)

    def test_a_dropped_connection_is_retried(self) -> None:
        calls = {"n": 0}
        slept: list[float] = []
        secret = "secret-query"  # nosec B105

        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.URLError(TimeoutError("timed out"))
            return _Response(b"ok")

        text = http_client.get_text(f"https://example.com/x?token={secret}", opener=opener, sleep=slept.append)
        self.assertEqual(text, "ok")
        self.assertEqual(calls["n"], 3)
        self.assertEqual(slept, [0.5, 1.0])

        def fail(_request: object, timeout: float) -> _Response:
            del timeout
            raise http.client.IncompleteRead(b"partial")

        with self.assertRaises(http_client.HttpTransportError) as raised:
            http_client.get_text(f"https://data.example.com/v2?token={secret}", opener=fail, sleep=lambda _s: None)
        self.assertEqual(str(raised.exception), "connection failed host=data.example.com attempts=4")
        self.assertNotIn(secret, str(raised.exception))

        def certificate(_request: object, timeout: float) -> _Response:
            del timeout
            calls["n"] += 1
            raise urllib.error.URLError(ssl.SSLError("certificate verify failed"))

        calls["n"] = 0
        with self.assertRaises(urllib.error.URLError):
            http_client.get_text("https://example.com/x", opener=certificate, sleep=self.fail)
        self.assertEqual(calls["n"], 1)

    def test_the_status_text_keeps_the_message_only(self) -> None:
        body = b'{"message":"invalid symbol: BAD","echo":"secret-query"}'

        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            raise _http_error(400, body)

        with self.assertRaises(http_client.HttpStatusError) as raised:
            http_client.get_text("https://example.com/x?token=secret-query", opener=opener, sleep=self.fail)
        self.assertEqual(str(raised.exception), "HTTP 400 invalid symbol: BAD")
        self.assertNotIn("secret-query", str(raised.exception))
        self.assertEqual(raised.exception.body, body.decode())

    def test_retries_stop_after_four_attempts(self) -> None:
        calls = {"n": 0}
        slept: list[float] = []

        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            calls["n"] += 1
            raise _http_error(503, b"later")

        with self.assertRaises(http_client.HttpStatusError) as raised:
            http_client.get_text("https://example.com/x", opener=opener, sleep=slept.append)
        self.assertEqual(calls["n"], 4)
        self.assertEqual(len(slept), 3)
        self.assertEqual(raised.exception.status, 503)

    def test_headers_are_not_logged(self) -> None:
        records: list[logging.LogRecord] = []
        handler = _Capture(records)
        logger = logging.getLogger("http_client")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        secret = "header-value-do-not-log"  # nosec B105

        def opener(_request: object, timeout: float) -> _Response:
            del timeout
            raise _http_error(500, b"down")

        try:
            with self.assertRaises(http_client.HttpStatusError):
                http_client.get_text(
                    "https://example.com/x",
                    headers={"Authorization": secret},
                    opener=opener,
                    sleep=lambda _seconds: None,
                )
        finally:
            logger.removeHandler(handler)
        dumped = json.dumps([record.getMessage() for record in records])
        self.assertNotIn(secret, dumped)

    def test_rate_limiter_waits_after_the_first_call(self) -> None:
        clock = {"t": 0.0}
        slept: list[float] = []

        def now() -> float:
            return clock["t"]

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            clock["t"] += seconds

        limiter = http_client.RateLimiter(2, sleep=sleep, clock=now)
        limiter.wait()
        limiter.wait()
        self.assertEqual(slept, [0.5])


if __name__ == "__main__":
    unittest.main()
