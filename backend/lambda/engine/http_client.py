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
_MAX_RETRY_AFTER = 5.0

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


def _decode(payload: bytes, errors: str) -> str:
    """``fallback`` is UTF-8, then Latin-1, so one stray byte does not fail the body."""
    if errors == "fallback":
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload.decode("latin-1")
    return payload.decode("utf-8", errors)


def _once(
    url: str,
    headers: dict[str, str],
    timeout: float,
    opener: Opener,
    retry_on: frozenset[int],
    errors: str,
) -> str:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener(request, timeout=timeout) as response:
            return _decode(response.read(), errors)
    except urllib.error.HTTPError as exc:
        payload = _read_http_error(exc).decode("utf-8", "replace")
        if exc.code in retry_on or 500 <= exc.code <= 599:
            raise _Retry(exc.code, payload, _retry_after(exc)) from None
        raise HttpStatusError(exc.code, payload) from None


def get_text(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
    *,
    opener: Opener | None = None,
    sleep: Sleeper = time.sleep,
    retry_on: frozenset[int] | None = None,
    errors: str = "strict",
) -> str:
    """GET a text body. Retries 429 and 5xx, plus ``retry_on``, at most four times."""
    fetch = opener or urllib.request.urlopen
    sent = headers or {}
    extra = frozenset({429}) if retry_on is None else frozenset(retry_on) | {429}
    delay = _BACKOFF_SECONDS
    last: _Retry | None = None
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            return _once(url, sent, timeout, fetch, extra, errors)
        except _Retry as exc:
            last = exc
            logger.info("http retry status=%s attempt=%s", exc.status, attempt)
            if exc.delay is not None and exc.delay > _MAX_RETRY_AFTER:
                break
            if attempt == _ATTEMPTS:
                break
            wait = delay if exc.delay is None or exc.delay < 0 else exc.delay
            sleep(wait)
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
