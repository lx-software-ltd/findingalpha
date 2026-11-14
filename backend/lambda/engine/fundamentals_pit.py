"""Point-in-time fundamentals. A number is invisible before its filing date."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

FLOW_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})
_BUCKETS = (
    ("quarter", 80, 100),
    ("half", 170, 190),
    ("nine_months", 260, 285),
    ("year", 350, 380),
)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


def period_class(start: date, end: date) -> str | None:
    days = (end - start).days
    for name, low, high in _BUCKETS:
        if low <= days <= high:
            return name
    return None


def normalise(company_facts: dict[str, Any], tag_map: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Turn a companyfacts payload into rows. USD facts only, 10-K and 10-Q only."""
    facts = company_facts.get("facts") or {}
    us_gaap = facts.get("us-gaap") or {}
    dei = facts.get("dei") or {}
    rows: list[dict[str, Any]] = []
    for field, tags in tag_map.items():
        kind = "stock" if field in {"equity", "cash", "longTermDebt", "shortTermDebt", "totalAssets", "sharesOutstanding"} else "flow"
        for tag in tags:
            source = dei if tag.startswith("dei:") else us_gaap
            concept = source.get(tag.removeprefix("dei:")) or {}
            units = concept.get("units") or {}
            series = units.get("shares") if field == "sharesOutstanding" else units.get("USD")
            for fact in series or []:
                form = str(fact.get("form") or "")
                if form not in FLOW_FORMS:
                    continue
                end = _as_date(fact.get("end"))
                filed = _as_date(fact.get("filed"))
                if end is None or filed is None or "val" not in fact:
                    continue
                start = _as_date(fact.get("start")) or end
                if kind == "flow" and period_class(start, end) is None:
                    continue
                rows.append(
                    {
                        "field": field,
                        "kind": kind,
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "value": fact["val"],
                        "filed": filed.isoformat(),
                        "form": form,
                        "fy": fact.get("fy"),
                        "fp": fact.get("fp"),
                    }
                )
    return rows


def as_of(rows: list[dict[str, Any]], on: str) -> list[dict[str, Any]]:
    """Rows filed on or before ``on``. One row per field and period: the latest filing."""
    chosen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if row["filed"] > on:
            continue
        key = (row["field"], row["start"], row["end"])
        current = chosen.get(key)
        if current is None or row["filed"] > current["filed"]:
            chosen[key] = row
    return list(chosen.values())


def _class_of(row: dict[str, Any]) -> str | None:
    return period_class(_as_date(row["start"]) or date.min, _as_date(row["end"]) or date.min)


def ttm(rows_as_of: list[dict[str, Any]], field: str) -> float | None:
    """Trailing twelve months: FY + YTD - YTD_prev, or FY when no later year-to-date exists."""
    flows = [row for row in rows_as_of if row["field"] == field and row["kind"] == "flow"]
    annual = [row for row in flows if _class_of(row) == "year"]
    if not annual:
        return None
    fy = max(annual, key=lambda row: row["end"])
    later = [row for row in flows if _class_of(row) != "year" and row["end"] > fy["end"]]
    if not later:
        return float(fy["value"])
    ytd = max(later, key=lambda row: row["end"])
    ytd_end = _as_date(ytd["end"])
    assert ytd_end is not None
    target = ytd_end - timedelta(days=365)
    same = [row for row in flows if _class_of(row) == _class_of(ytd)]
    previous = [
        row
        for row in same
        if row["end"] < ytd["end"] and abs((_as_date(row["end"]) - target).days) <= 20  # type: ignore[operator]
    ]
    if not previous:
        return None
    prev = min(previous, key=lambda row: abs((_as_date(row["end"]) - target).days))  # type: ignore[operator]
    return float(fy["value"]) + float(ytd["value"]) - float(prev["value"])


def latest_stock(rows_as_of: list[dict[str, Any]], field: str) -> float | None:
    stocks = [row for row in rows_as_of if row["field"] == field and row["kind"] == "stock"]
    if not stocks:
        return None
    return float(max(stocks, key=lambda row: row["end"])["value"])


def average_stock(rows_as_of: list[dict[str, Any]], field: str) -> float | None:
    """Mean of the latest stock value and the value about four quarters earlier."""
    stocks = [row for row in rows_as_of if row["field"] == field and row["kind"] == "stock"]
    if not stocks:
        return None
    latest = max(stocks, key=lambda row: row["end"])
    latest_end = _as_date(latest["end"])
    assert latest_end is not None
    target = latest_end - timedelta(days=365)
    earlier = [
        row
        for row in stocks
        if row is not latest and abs((_as_date(row["end"]) - target).days) <= 45  # type: ignore[operator]
    ]
    if not earlier:
        return None
    prior = min(earlier, key=lambda row: abs((_as_date(row["end"]) - target).days))  # type: ignore[operator]
    return (float(latest["value"]) + float(prior["value"])) / 2
