"""Alpaca market data.

The paper secret is read at call time. Headers are never logged.
Daily bars use ``feed=sip``. See ``docs/research/data-sources.md``.
"""

from __future__ import annotations

import os
import urllib.parse
from collections.abc import Iterator
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import http_client
import secrets_read

_SECRET_ID = "findingalpha/alpaca-paper"
_PAPER = "https://paper-api.alpaca.markets"
_DATA = "https://data.alpaca.markets"
_BATCH = 200
_PER_SECOND = 150 / 60
_FEED = "sip"
_ADJUSTMENTS = frozenset({"raw", "split", "dividend", "all"})
_STATUSES = frozenset({"active", "inactive"})
_ACTION_GROUPS = (
    ("cash_dividends", "cash_dividend"),
    ("forward_splits", "forward_split"),
    ("reverse_splits", "reverse_split"),
)
_NEW_YORK = ZoneInfo("America/New_York")
_CLIENT: AlpacaData | None = None


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


def _day(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if len(text) < 10:
        raise ValueError("date must be YYYY-MM-DD")
    date.fromisoformat(text[:10])
    return text[:10]


def _instant(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
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
    }


def _bar(symbol: str, row: object) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("bar is not an object")
    return {
        "symbol": symbol,
        "date": _session_date(str(row["t"])),
        "open": row["o"],
        "high": row["h"],
        "low": row["l"],
        "close": row["c"],
        "volume": row["v"],
        "vwap": row["vw"],
    }


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
        "payDate": row.get("payable_date"),
        "cashPerShare": row.get("rate") if dividend else None,
        "splitFrom": None if dividend else row.get("old_rate"),
        "splitTo": None if dividend else row.get("new_rate"),
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


class AlpacaData:
    """One client shares the rate limit across its calls."""

    def __init__(
        self,
        *,
        key_id: str,
        secret_key: str,
        secret_id: str = _SECRET_ID,
        opener: http_client.Opener | None = None,
        limiter: Any = None,
    ) -> None:
        if _unsafe(key_id) or _unsafe(secret_key):
            raise secrets_read.NotConfigured(secret_id)
        self._key_id = key_id
        self._secret_key = secret_key
        self._opener = opener
        self._limiter = limiter if limiter is not None else http_client.RateLimiter(_PER_SECOND)

    def __repr__(self) -> str:
        return "AlpacaData()"

    def _headers(self) -> dict[str, str]:
        return {"APCA-API-KEY-ID": self._key_id, "APCA-API-SECRET-KEY": self._secret_key}

    def _json(self, url: str) -> Any:
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
            yield payload
            nxt = payload.get("next_page_token")
            if not isinstance(nxt, str) or not nxt or nxt in seen:
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
        if not clean:
            return
        params = {
            "timeframe": "1Day",
            "start": _day(start),
            "end": _day(end),
            "adjustment": adjustment,
            "feed": _FEED,
            "limit": "10000",
        }
        for batch in _chunks(clean, _BATCH):
            params["symbols"] = ",".join(batch)
            for payload in self._pages(f"{_DATA}/v2/stocks/bars", params):
                bars = payload.get("bars")
                if bars is None:
                    continue
                if not isinstance(bars, dict):
                    raise ValueError("bars response is not a symbol map")
                for symbol, rows in bars.items():
                    if not isinstance(rows, list):
                        raise ValueError("bars response is not a symbol map")
                    for row in rows:
                        yield _bar(str(symbol), row)

    def corporate_actions(self, start: date | datetime | str, end: date | datetime | str) -> list[dict[str, Any]]:
        """Cash dividends and splits with an ex-date inside the window."""
        params = {
            "types": "cash_dividend,forward_split,reverse_split",
            "start": _day(start),
            "end": _day(end),
            "limit": "100",
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
        params = {
            "symbols": ",".join(clean),
            "start": _instant(start),
            "end": _instant(end),
            "limit": "50",
        }
        found: list[dict[str, Any]] = []
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
) -> AlpacaData:
    """Build a client from the paper secret. The value is not logged."""
    secret_id = os.environ.get("ALPACA_SECRET_ID") or _SECRET_ID
    payload = secrets_read.read_json_secret(secret_id, ("key_id", "secret_key"), client=secret_client)
    return AlpacaData(
        key_id=str(payload["key_id"]),
        secret_key=str(payload["secret_key"]),
        secret_id=secret_id,
        opener=opener,
        limiter=limiter,
    )


def _shared() -> AlpacaData:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = client_from_secret()
    return _CLIENT


def list_assets(status: str = "active") -> list[dict[str, Any]]:
    return _shared().list_assets(status)


def daily_bars(
    symbols: list[str] | tuple[str, ...],
    start: date | datetime | str,
    end: date | datetime | str,
    adjustment: str,
) -> Iterator[dict[str, Any]]:
    return _shared().daily_bars(symbols, start, end, adjustment)


def corporate_actions(start: date | datetime | str, end: date | datetime | str) -> list[dict[str, Any]]:
    return _shared().corporate_actions(start, end)


def news(
    symbols: list[str] | tuple[str, ...],
    start: date | datetime | str,
    end: date | datetime | str,
) -> list[dict[str, Any]]:
    return _shared().news(symbols, start, end)
