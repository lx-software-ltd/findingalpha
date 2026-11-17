"""Daily bars requests that survive one rejected symbol."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import http_client

logger = logging.getLogger(__name__)

_SKIP_LIMIT = 20
_NEW_YORK = ZoneInfo("America/New_York")
_SIP_LAG = timedelta(minutes=16)
_CLOSE = time(16, 0)


def _moment(now: datetime | None) -> datetime:
    moment = now or datetime.now(_NEW_YORK)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=_NEW_YORK)
    return moment.astimezone(_NEW_YORK)


def session_available(day: str, now: datetime | None = None) -> bool:
    """The 16:00 close is at least 16 minutes in the past."""
    session = date.fromisoformat(str(day)[:10])
    close = datetime.combine(session, _CLOSE, tzinfo=_NEW_YORK)
    return _moment(now) - _SIP_LAG >= close


def sip_end(day: str, now: datetime | None = None) -> str:
    """The ``end`` for a SIP daily request.

    Alpaca reads a bare date through the end of that New York day, and the
    free plan refuses an end inside the last 15 minutes. A day whose end is
    outside that window stays a date. Once the 16:00 close is outside it,
    the day is a timestamp 16 minutes ago. The extra minute covers a clock
    that is slightly ahead. A close still inside the window is not requested.
    """
    session = date.fromisoformat(str(day)[:10])
    moment = _moment(now)
    day_end = datetime.combine(session + timedelta(days=1), time.min, tzinfo=_NEW_YORK)
    safe = moment - _SIP_LAG
    if day_end <= safe:
        return session.isoformat()
    if not session_available(day, moment):
        return (session - timedelta(days=1)).isoformat()
    return safe.isoformat(timespec="seconds")


Fetch = Callable[[str, dict[str, str]], Iterator[dict[str, Any]]]
Rows = Callable[[dict[str, Any]], Iterator[dict[str, Any]]]
Shape = dict[tuple[str, str, str], bool]


class _Split:
    """Skips shared by every batch of one request, and remembered afterwards."""

    def __init__(self, skipped: set[str], limit: int) -> None:
        self.skipped = skipped
        self.limit = limit
        self.found = 0
        self.shape: Shape = {}


def daily(
    fetch: Fetch,
    symbols: list[str],
    start: str,
    end: str,
    adjustment: str,
    *,
    feed: str,
    batch: int,
    endpoint: str,
    rows_of: Rows,
    skipped: set[str],
    probe: str = "SPY",
    limit: int = _SKIP_LIMIT,
) -> Iterator[dict[str, Any]]:
    """Yield bars for ``symbols``, at most ``batch`` per request.

    A symbol already in ``skipped`` is not requested again. A 400 on several
    symbols is split in half. One new symbol is skipped when ``probe`` still
    answers. More than ``limit`` new skips, or a 400 on ``probe``, is raised.
    """
    params = {
        "timeframe": "1Day",
        "start": start,
        "end": end,
        "adjustment": adjustment,
        "feed": feed,
        "limit": "10000",
    }
    state = _Split(skipped, limit)
    for start_at in range(0, len(symbols), batch):
        group = [symbol for symbol in symbols[start_at : start_at + batch] if symbol not in skipped]
        yield from _batch(fetch, params, group, endpoint=endpoint, rows_of=rows_of, probe=probe, state=state)


def _batch(
    fetch: Fetch,
    params: dict[str, str],
    symbols: list[str],
    *,
    endpoint: str,
    rows_of: Rows,
    probe: str,
    state: _Split,
) -> Iterator[dict[str, Any]]:
    if not symbols:
        return
    query = dict(params)
    query["symbols"] = ",".join(symbols)
    try:
        pages = list(fetch(endpoint, query))
    except http_client.HttpStatusError as exc:
        if exc.status != 400:
            raise
        if len(symbols) > 1:
            if not _probe_ok(fetch, params, endpoint, probe, state):
                raise
            mid = len(symbols) // 2
            yield from _batch(
                fetch, params, symbols[:mid], endpoint=endpoint, rows_of=rows_of, probe=probe, state=state
            )
            yield from _batch(
                fetch, params, symbols[mid:], endpoint=endpoint, rows_of=rows_of, probe=probe, state=state
            )
            return
        if symbols[0] != probe and _probe_ok(fetch, params, endpoint, probe, state):
            state.found += 1
            state.skipped.add(symbols[0])
            if state.found > state.limit:
                raise
            logger.info("alpaca bars skipped symbol=%s", symbols[0])
            return
        raise
    state.shape[_key(params)] = True
    for payload in pages:
        yield from rows_of(payload)


def _key(params: dict[str, str]) -> tuple[str, str, str]:
    return (params.get("start", ""), params.get("end", ""), params.get("adjustment", ""))


def _probe_ok(fetch: Fetch, params: dict[str, str], endpoint: str, probe: str, state: _Split) -> bool:
    key = _key(params)
    if key in state.shape:
        return state.shape[key]
    query = dict(params)
    query["symbols"] = probe
    try:
        list(fetch(endpoint, query))
    except http_client.HttpStatusError as exc:
        if exc.status != 400:
            raise
        state.shape[key] = False
        return False
    state.shape[key] = True
    return True
