"""HTTP GET with retries. Headers are never written to the log."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Callable

logger = logging.getLogger(__name__)

_ATTEMPTS = 4
_BACKOFF_SECONDS = 0.5

Opener = Callable[..., Any]
Sleeper = Callable[[float], None]


class HttpStatusError(Exception):
    """The server answered with a status that is not retried, or retries ran out."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body


class _Retry(Exception):
    def __init__(self, status: int, body: str, delay: float | None) -> None:
        super().__init__(status)
        self.status = status
        self.body = body
        self.delay = delay


def _read_http_error(exc: urllib.error.HTTPError) -> bytes:
    try:
        return exc.read()
    finally:
        exc.close()


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    raw = exc.headers.get("Retry-After") if exc.headers else None
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _once(url: str, headers: dict[str, str], timeout: float, opener: Opener) -> str:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        payload = _read_http_error(exc).decode("utf-8", "replace")
        if exc.code == 429 or 500 <= exc.code <= 599:
            raise _Retry(exc.code, payload, _retry_after(exc)) from None
        raise HttpStatusError(exc.code, payload) from None


def get_text(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
    *,
    opener: Opener | None = None,
    sleep: Sleeper = time.sleep,
) -> str:
    """GET a text body. Retries 429 and 5xx at most four times."""
    fetch = opener or urllib.request.urlopen
    sent = headers or {}
    delay = _BACKOFF_SECONDS
    last: _Retry | None = None
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            return _once(url, sent, timeout, fetch)
        except _Retry as exc:
            last = exc
            logger.info("http retry status=%s attempt=%s", exc.status, attempt)
            if attempt == _ATTEMPTS:
                break
            sleep(exc.delay if exc.delay is not None else delay)
            delay *= 2
    assert last is not None
    raise HttpStatusError(last.status, last.body)


def get_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
    **kwargs: Any,
) -> Any:
    return json.loads(get_text(url, headers, timeout, **kwargs))


class RateLimiter:
    """Sleep so calls stay at or under ``per_second``."""

    def __init__(
        self,
        per_second: float,
        *,
        sleep: Sleeper = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if per_second <= 0:
            raise ValueError("per_second must be positive")
        self._gap = 1.0 / per_second
        self._sleep = sleep
        self._clock = clock
        self._next = 0.0

    def wait(self) -> None:
        now = self._clock()
        if now < self._next:
            self._sleep(self._next - now)
            now = self._clock()
        self._next = now + self._gap
