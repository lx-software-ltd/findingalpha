"""One company's inputs as of a date. Later facts and prices stay out."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import fundamentals_pit

_BALANCE_SHEET = frozenset(
    {
        "totalAssets",
        "currentAssets",
        "currentLiabilities",
        "totalLiabilities",
        "equity",
        "cash",
        "shortTermInvestments",
    }
)
_DEBT_FIELDS = ("longTermDebt", "shortTermDebt")


def build(
    symbol: str,
    cik: str,
    day: date | str,
    pit_rows: list[dict[str, Any]],
    adjusted_bars: list[dict[str, Any]],
    raw_close: float | None,
    shares_outstanding: float | None,
    sessions: list[Any] | None = None,
) -> dict[str, Any]:
    """Trailing figures, stock averages, market cap, and closes on or before ``day``.

    ``sessions`` is the market calendar. Closes are aligned to it, and a
    session with no print keeps the previous close, so a gap does not move
    the 21, 200, and 252 session windows. Without it, one close is kept per
    date the symbol printed.
    """
    on = day.isoformat() if isinstance(day, date) else str(day)[:10]
    visible = fundamentals_pit.as_of(list(pit_rows), on)
    maps = fundamentals_pit.load_tag_maps()
    body: dict[str, Any] = {"symbol": symbol, "cik": cik, "asOf": on}
    for field in maps.get("flows") or {}:
        body[f"{field}_ttm"] = fundamentals_pit.ttm(visible, field)
    for field in maps.get("stocks") or {}:
        body[field] = fundamentals_pit.latest_stock(visible, field)
        body[f"{field}_avg"] = fundamentals_pit.average_stock(visible, field)
    _apply_debt_policy(body, visible)
    body["closes"] = _closes(adjusted_bars, on, sessions)
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


def _statement_ends(rows: list[dict[str, Any]]) -> list[str]:
    ends = {str(row["end"]) for row in rows if row.get("kind") == "stock" and row.get("field") in _BALANCE_SHEET}
    return sorted(ends)


def _prior_statement(ends: list[str], latest: str) -> str | None:
    latest_day = date.fromisoformat(latest)
    target = latest_day - timedelta(days=365)
    earlier = [end for end in ends if end != latest and abs((date.fromisoformat(end) - target).days) <= 45]
    if not earlier:
        return None
    return min(earlier, key=lambda end: abs((date.fromisoformat(end) - target).days))


def _debt_on(rows: list[dict[str, Any]], field: str, end: str) -> float | None:
    found = [row for row in rows if row.get("field") == field and row.get("kind") == "stock" and row.get("end") == end]
    if not found:
        return None
    return float(max(found, key=lambda row: str(row.get("filed")))["value"])


def _apply_debt_policy(body: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Follow the register when a debt tag is missing.

    ``unreportedDebt: zero`` means a balance sheet that never reports the
    tag, or drops it after an older statement, has zero of that debt.
    The average uses the same rule on the prior statement.
    """
    import methodology

    policy = methodology.load().get("fundamentals") or {}
    if policy.get("unreportedDebt") != "zero":
        return
    ends = _statement_ends(rows)
    if not ends:
        return
    latest = ends[-1]
    prior = _prior_statement(ends, latest)
    for field in _DEBT_FIELDS:
        filed_ends = [str(row.get("end")) for row in rows if row.get("field") == field and row.get("kind") == "stock"]
        newest = max(filed_ends) if filed_ends else None
        if newest is None or newest < latest:
            body[field] = 0
        on_latest = _debt_on(rows, field, latest)
        if on_latest is not None:
            body[field] = on_latest
        if prior is None or body.get(field) is None:
            continue
        on_prior = _debt_on(rows, field, prior)
        body[f"{field}_avg"] = (float(body[field]) + float(0 if on_prior is None else on_prior)) / 2


def _closes(
    bars: list[dict[str, Any]],
    on: str,
    sessions: list[Any] | None,
) -> list[float | None]:
    by_day: dict[str, float | None] = {}
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        day = _day(bar.get("date"))
        if day is None or day > on:
            continue
        close = bar.get("close")
        if isinstance(close, bool) or not isinstance(close, (int, float)):
            by_day[day] = None
        else:
            by_day[day] = float(close)
    if not sessions:
        return [by_day[day] for day in sorted(by_day)]
    series: list[float | None] = []
    last: float | None = None
    for raw in sessions:
        day = _day(raw)
        if day is None or day > on:
            continue
        if day in by_day and by_day[day] is not None:
            last = by_day[day]
        series.append(last)
    return series


def _day(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return None
    text = str(value)[:10]
    return text or None
