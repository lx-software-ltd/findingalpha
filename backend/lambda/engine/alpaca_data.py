"""Alpaca market data. The paper secret is read when a call is made."""

from __future__ import annotations

import os
import time
import urllib.parse
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import alpaca_bars
import http_client
import secrets_read

_SECRET_ID = "findingalpha/alpaca-paper"
_PAPER = "https://paper-api.alpaca.markets"
_DATA = "https://data.alpaca.markets"
_BATCH = 200
_PER_MINUTE = 150
_PER_SECOND = _PER_MINUTE / 60
_FEED = "sip"
_ADJUSTMENTS = frozenset({"raw", "split", "dividend", "all"})
_STATUSES = frozenset({"active", "inactive"})
_ACTION_GROUPS = (
    ("cash_dividends", "cash_dividend"),
    ("forward_splits", "forward_split"),
    ("reverse_splits", "reverse_split"),
)
_BAR_FIELDS = (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"), ("v", "volume"), ("vw", "vwap"))
_RATE_PK = "RATE#alpaca"
_RATE_SK = "MINUTE"
_NEW_YORK = ZoneInfo("America/New_York")
_CLIENT: AlpacaData | None = None
_LIMITER: http_client.RateLimiter | None = None
_SECRET_CLIENT: Any = None
_OPENER: http_client.Opener | None = None
_INGEST: Callable[[], bool] | None = None
_RESERVE: Callable[[], None] | None = None
_HOLD = False


class IngestDisabled(Exception):
    """``IngestEnabled`` is off, so no request was sent."""


@contextmanager
def hold_ingest_check() -> Iterator[None]:
    global _HOLD
    previous = _HOLD
    _HOLD = True
    try:
        yield
    finally:
        _HOLD = previous


class AlpacaRateLimited(Exception):
    pass


def _unsafe(value: object) -> bool:
    if not isinstance(value, str):
        return True
    text = value.strip()
    return not text or any(char in value for char in "\r\n")


def _url(base: str, params: dict[str, str]) -> str:
    return f"{base}?{urllib.parse.urlencode(params)}"


def _symbols(symbols: object) -> list[str]:
    if isinstance(symbols, str) or not isinstance(symbols, (list, tuple)):
        raise ValueError("symbols must be a list")
    found: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        symbol = str(raw).strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        found.append(symbol)
    return found


def _chunks(items: list[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _as_new_york(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_NEW_YORK)
    return value.astimezone(_NEW_YORK)


def _day(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return _as_new_york(value).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if len(text) < 10:
        raise ValueError("date must be YYYY-MM-DD")
    date.fromisoformat(text[:10])
    return text[:10]


def _instant(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        moment = _as_new_york(value).astimezone(timezone.utc)
        return moment.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        raise ValueError("time is required")
    return text


def _session_date(timestamp: str) -> str:
    """The New York session date of a daily bar timestamp."""
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(_NEW_YORK).date().isoformat()


def _optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _asset(row: object) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    symbol = str(row.get("symbol") or "").strip()
    if not symbol:
        return None
    return {
        "symbol": symbol,
        "name": str(row.get("name") or ""),
        "exchange": str(row.get("exchange") or ""),
        "status": str(row.get("status") or ""),
        "tradable": bool(row.get("tradable")),
        "marginable": bool(row.get("marginable")),
        "shortable": bool(row.get("shortable")),
        "fractionable": bool(row.get("fractionable")),
        "assetClass": str(row.get("class") or ""),
        "id": str(row.get("id") or ""),
    }


def _bar(symbol: str, row: object) -> dict[str, Any]:
    if not isinstance(row, dict) or any(key not in row for key, _name in _BAR_FIELDS) or "t" not in row:
        raise ValueError("bar is missing a field")
    mapped = {name: row[key] for key, name in _BAR_FIELDS}
    return {"symbol": symbol, "date": _session_date(str(row["t"])), **mapped}


def _bar_rows(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    bars = payload.get("bars")
    if bars is None:
        return
    if not isinstance(bars, dict):
        raise ValueError("bars response is not a symbol map")
    for symbol, rows in bars.items():
        if not isinstance(rows, list):
            raise ValueError("bars response is not a symbol map")
        for row in rows:
            yield _bar(str(symbol), row)


def _action(kind: str, row: object) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    symbol = str(row.get("symbol") or "").strip()
    if not symbol:
        return None
    dividend = kind == "cash_dividend"
    return {
        "symbol": symbol,
        "type": kind,
        "exDate": row.get("ex_date"),
        "processDate": row.get("process_date"),
        "payDate": row.get("payable_date"),
        "cashPerShare": row.get("rate") if dividend else None,
        "splitFrom": None if dividend else row.get("old_rate"),
        "splitTo": None if dividend else row.get("new_rate"),
        "special": row.get("special") if dividend else None,
        "foreign": row.get("foreign") if dividend else None,
        "subType": _optional(row.get("sub_type")) if dividend else None,
        "newSymbol": None if dividend else _optional(row.get("new_symbol")),
    }


def _news(row: object) -> dict[str, Any] | None:
    if not isinstance(row, dict) or row.get("id") is None:
        return None
    raw_symbols = row.get("symbols")
    symbols = [str(item) for item in raw_symbols] if isinstance(raw_symbols, list) else []
    return {
        "id": row["id"],
        "symbols": symbols,
        "headline": str(row.get("headline") or ""),
        "summary": str(row.get("summary") or ""),
        "source": str(row.get("source") or ""),
        "url": str(row.get("url") or ""),
        "createdAt": str(row.get("created_at") or ""),
    }


def take_minute_slot(
    update: Callable[..., Any],
    *,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    cap: int = _PER_MINUTE,
    attempts: int = 8,
) -> None:
    from store import ConditionNotMet

    names = {"#n": "count", "#w": "window"}
    for _ in range(attempts):
        minute = int(clock() // 60)
        try:
            update(
                _RATE_PK,
                _RATE_SK,
                "ADD #n :one",
                {":one": 1, ":cap": cap, ":minute": minute},
                "#w = :minute AND #n < :cap",
                names,
            )
            return
        except ConditionNotMet:
            pass
        try:
            update(
                _RATE_PK,
                _RATE_SK,
                "SET #w = :minute, #n = :one",
                {":one": 1, ":minute": minute},
                "attribute_not_exists(#w) OR #w <> :minute",
                names,
            )
            return
        except ConditionNotMet:
            pass
        now = clock()
        remain = (int(now // 60) + 1) * 60 - now
        sleep(remain if remain > 0 else 0.05)
    raise AlpacaRateLimited()


def _reserve_shared_slot() -> None:
    if _RESERVE is not None:
        _RESERVE()
        return
    from config import MissingSetting, records_table_name

    try:
        records_table_name()
    except MissingSetting:
        return
    import store

    take_minute_slot(store.update_conditional)


class _Gate:
    def __init__(self, local: Any, reserve: Callable[[], None]) -> None:
        self._local = local
        self._reserve = reserve

    def wait(self) -> None:
        self._local.wait()
        self._reserve()


def _process_limiter() -> http_client.RateLimiter:
    global _LIMITER
    if _LIMITER is None:
        _LIMITER = http_client.RateLimiter(_PER_SECOND)
    return _LIMITER


def _default_ingest_enabled() -> bool:
    import kill_switch

    return kill_switch.is_enabled("ingestEnabled")


class AlpacaData:
    """One client. A shared limiter is passed in when calls share a cap."""

    def __init__(
        self,
        *,
        key_id: str,
        secret_key: str,
        secret_id: str = _SECRET_ID,
        opener: http_client.Opener | None = None,
        limiter: Any = None,
        ingest_enabled: Callable[[], bool] | None = None,
    ) -> None:
        if _unsafe(key_id) or _unsafe(secret_key):
            raise secrets_read.NotConfigured(secret_id)
        self._key_id = key_id.strip()
        self._secret_key = secret_key.strip()
        self._opener = opener
        self._limiter = limiter if limiter is not None else http_client.RateLimiter(_PER_SECOND)
        self._ingest_enabled = ingest_enabled
        self._skipped: set[str] = set()

    def __repr__(self) -> str:
        return "AlpacaData()"

    def _headers(self) -> dict[str, str]:
        return {"APCA-API-KEY-ID": self._key_id, "APCA-API-SECRET-KEY": self._secret_key}

    def _allow(self) -> None:
        if _HOLD:
            return
        check = self._ingest_enabled if self._ingest_enabled is not None else _default_ingest_enabled
        if not check():
            raise IngestDisabled()

    def _json(self, url: str) -> Any:
        self._allow()
        self._limiter.wait()
        return http_client.get_json(url, self._headers(), opener=self._opener)

    def _pages(self, url: str, params: dict[str, str]) -> Iterator[dict[str, Any]]:
        seen: set[str] = set()
        token: str | None = None
        while True:
            query = dict(params)
            if token:
                query["page_token"] = token
            payload = self._json(_url(url, query))
            if not isinstance(payload, dict):
                raise ValueError("response is not an object")
            nxt = payload.get("next_page_token")
            if isinstance(nxt, str) and nxt in seen:
                raise ValueError("repeated page token")
            yield payload
            if not isinstance(nxt, str) or not nxt:
                return
            seen.add(nxt)
            token = nxt

    def list_assets(self, status: str = "active") -> list[dict[str, Any]]:
        """Active US equities, unless ``status`` is ``inactive``."""
        if status not in _STATUSES:
            raise ValueError("status must be active or inactive")
        payload = self._json(_url(f"{_PAPER}/v2/assets", {"status": status, "asset_class": "us_equity"}))
        if not isinstance(payload, list):
            raise ValueError("asset response is not a list")
        found: list[dict[str, Any]] = []
        for row in payload:
            asset = _asset(row)
            if asset is not None:
                found.append(asset)
        return found

    def daily_bars(
        self,
        symbols: list[str] | tuple[str, ...],
        start: date | datetime | str,
        end: date | datetime | str,
        adjustment: str,
    ) -> Iterator[dict[str, Any]]:
        """SIP daily bars. One request covers at most 200 symbols."""
        if adjustment not in _ADJUSTMENTS:
            raise ValueError("adjustment must be raw, split, dividend, or all")
        clean = _symbols(symbols)
        start_day = _day(start)
        end_day = _day(end)
        return self._daily_bars(clean, start_day, end_day, adjustment)

    def _daily_bars(self, symbols: list[str], start: str, end: str, adjustment: str) -> Iterator[dict[str, Any]]:
        if not symbols:
            return
        yield from alpaca_bars.daily(
            self._pages,
            symbols,
            start,
            end,
            adjustment,
            feed=_FEED,
            batch=_BATCH,
            endpoint=f"{_DATA}/v2/stocks/bars",
            rows_of=_bar_rows,
            skipped=self._skipped,
        )

    def corporate_actions(self, start: date | datetime | str, end: date | datetime | str) -> list[dict[str, Any]]:
        """Dividends and splits whose ``process_date`` is inside the window."""
        params = {
            "types": "cash_dividend,forward_split,reverse_split",
            "start": _day(start),
            "end": _day(end),
            "limit": "1000",
        }
        found: list[dict[str, Any]] = []
        for payload in self._pages(f"{_DATA}/v1/corporate-actions", params):
            groups = payload.get("corporate_actions") or {}
            if not isinstance(groups, dict):
                raise ValueError("corporate actions response is not grouped")
            for group, kind in _ACTION_GROUPS:
                rows = groups.get(group) or []
                if not isinstance(rows, list):
                    raise ValueError("corporate actions response is not grouped")
                for row in rows:
                    action = _action(kind, row)
                    if action is not None:
                        found.append(action)
        return found

    def news(
        self,
        symbols: list[str] | tuple[str, ...],
        start: date | datetime | str,
        end: date | datetime | str,
    ) -> list[dict[str, Any]]:
        """Headlines only. The article body is not copied."""
        clean = _symbols(symbols)
        if not clean:
            return []
        start_at = _instant(start)
        end_at = _instant(end)
        found: list[dict[str, Any]] = []
        for batch in _chunks(clean, _BATCH):
            params = {"symbols": ",".join(batch), "start": start_at, "end": end_at, "limit": "50"}
            for payload in self._pages(f"{_DATA}/v1beta1/news", params):
                rows = payload.get("news")
                if rows is None:
                    continue
                if not isinstance(rows, list):
                    raise ValueError("news response is not a list")
                for row in rows:
                    item = _news(row)
                    if item is not None:
                        found.append(item)
        return found


def client_from_secret(
    *,
    secret_client: Any = None,
    opener: http_client.Opener | None = None,
    limiter: Any = None,
    ingest_enabled: Callable[[], bool] | None = None,
    reserve: Callable[[], None] | None = None,
) -> AlpacaData:
    """Build a client from the paper secret. The value is not logged."""
    secret_id = os.environ.get("ALPACA_SECRET_ID") or _SECRET_ID
    reader = secret_client if secret_client is not None else _SECRET_CLIENT
    payload = secrets_read.read_json_secret(secret_id, ("key_id", "secret_key"), client=reader)
    if limiter is None:
        limiter = _Gate(_process_limiter(), reserve if reserve is not None else _reserve_shared_slot)
    return AlpacaData(
        key_id=str(payload["key_id"]),
        secret_key=str(payload["secret_key"]),
        secret_id=secret_id,
        opener=opener if opener is not None else _OPENER,
        limiter=limiter,
        ingest_enabled=ingest_enabled if ingest_enabled is not None else _INGEST,
    )


def _open() -> AlpacaData:
    return _CLIENT if _CLIENT is not None else client_from_secret()


def list_assets(status: str = "active") -> list[dict[str, Any]]:
    return _open().list_assets(status)


def daily_bars(
    symbols: list[str] | tuple[str, ...], start: date | datetime | str, end: date | datetime | str, adjustment: str
) -> Iterator[dict[str, Any]]:
    return _open().daily_bars(symbols, start, end, adjustment)


def corporate_actions(start: date | datetime | str, end: date | datetime | str) -> list[dict[str, Any]]:
    return _open().corporate_actions(start, end)


def news(
    symbols: list[str] | tuple[str, ...], start: date | datetime | str, end: date | datetime | str
) -> list[dict[str, Any]]:
    return _open().news(symbols, start, end)
