"""HTTP retries and the rate limiter."""

from __future__ import annotations

import io
import json
import logging
import unittest
import urllib.error
from email.message import Message

import http_client


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> bool:
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
        handler = logging.Handler()
        handler.emit = records.append  # type: ignore[method-assign]
        logger = logging.getLogger("http_client")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        secret = "header-value-do-not-log"

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
