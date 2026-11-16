"""One company's inputs as of a date. Later facts and prices stay out."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import fundamentals_pit


def build(
    symbol: str,
    cik: str,
    day: date | str,
    pit_rows: list[dict[str, Any]],
    adjusted_bars: list[dict[str, Any]],
    raw_close: float | None,
    shares_outstanding: float | None,
) -> dict[str, Any]:
    """Trailing figures, stock averages, market cap, and closes on or before ``day``."""
    on = day.isoformat() if isinstance(day, date) else str(day)[:10]
    visible = fundamentals_pit.as_of(list(pit_rows), on)
    maps = fundamentals_pit.load_tag_maps()
    body: dict[str, Any] = {"symbol": symbol, "cik": cik, "asOf": on}
    for field in maps.get("flows") or {}:
        body[f"{field}_ttm"] = fundamentals_pit.ttm(visible, field)
    for field in maps.get("stocks") or {}:
        body[field] = fundamentals_pit.latest_stock(visible, field)
        body[f"{field}_avg"] = fundamentals_pit.average_stock(visible, field)
    body["closes"] = _closes(adjusted_bars, on)
    body["marketCap"] = _product(raw_close, shares_outstanding)
    body["enterpriseValue"] = _enterprise_value(body)
    return body


def _product(left: float | None, right: float | None) -> float | None:
    if left is None or right is None or isinstance(left, bool) or isinstance(right, bool):
        return None
    return float(left) * float(right)


def _enterprise_value(body: dict[str, Any]) -> float | None:
    market = body.get("marketCap")
    long_debt = body.get("longTermDebt")
    short_debt = body.get("shortTermDebt")
    cash = body.get("cash")
    if None in (market, long_debt, short_debt, cash):
        return None
    value = float(market) + float(long_debt) + float(short_debt) - float(cash)
    if value <= 0:
        return None
    return value


def _closes(bars: list[dict[str, Any]], on: str) -> list[float | None]:
    parsed: list[tuple[str, float | None]] = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        day = _day(bar.get("date"))
        if day is None or day > on:
            continue
        close = bar.get("close")
        if isinstance(close, bool) or not isinstance(close, (int, float)):
            parsed.append((day, None))
        else:
            parsed.append((day, float(close)))
    parsed.sort(key=lambda item: item[0])
    return [close for _day, close in parsed]


def _day(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return None
    text = str(value)[:10]
    return text or None
