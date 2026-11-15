"""Point-in-time fundamentals. A number is invisible before its filing date."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

FLOW_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})
_SHARES_FIELD = "sharesOutstanding"
_BUCKETS = (
    ("quarter", 80, 100),
    ("half", 170, 190),
    ("nine_months", 260, 285),
    ("year", 350, 380),
)
_CONTRACT = Path(__file__).resolve().parent / "contracts" / "fundamentals.json"
TagMaps = dict[str, dict[str, list[str]]]


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


def load_tag_maps(path: Path | None = None) -> TagMaps:
    """Flows and stocks from the contract. Tag order is the preference order."""
    raw = json.loads((path or _CONTRACT).read_text(encoding="utf-8"))
    maps: TagMaps = {}
    for section in ("flows", "stocks"):
        fields = raw.get(section)
        if not isinstance(fields, dict) or not fields:
            raise ValueError(f"fundamentals contract is missing {section}")
        maps[section] = {str(field): [str(tag) for tag in tags] for field, tags in fields.items()}
    return maps


def _fact_rows(
    company_facts: dict[str, Any],
    field: str,
    tag: str,
    kind: str,
) -> list[dict[str, Any]]:
    facts = company_facts.get("facts") or {}
    source = (facts.get("dei") or {}) if tag.startswith("dei:") else (facts.get("us-gaap") or {})
    concept = source.get(tag.removeprefix("dei:")) or {}
    units = concept.get("units") or {}
    series = units.get("shares") if field == _SHARES_FIELD else units.get("USD")
    rows: list[dict[str, Any]] = []
    for fact in series or []:
        form = str(fact.get("form") or "")
        value = fact.get("val")
        if form not in FLOW_FORMS or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        end = _as_date(fact.get("end"))
        filed = _as_date(fact.get("filed"))
        if end is None or filed is None:
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
                "value": value,
                "filed": filed.isoformat(),
                "form": form,
                "fy": fact.get("fy"),
                "fp": fact.get("fp"),
            }
        )
    return rows


def normalise(company_facts: dict[str, Any], maps: TagMaps | None = None) -> list[dict[str, Any]]:
    """Turn a companyfacts payload into rows.

    USD only, except share counts. 10-K, 10-Q and their amendments only.
    The first tag that yields a row wins; later tags for that field are ignored.
    """
    chosen = maps if maps is not None else load_tag_maps()
    rows: list[dict[str, Any]] = []
    for kind, section in (("flow", "flows"), ("stock", "stocks")):
        for field, tags in chosen[section].items():
            for tag in tags:
                found = _fact_rows(company_facts, field, tag, kind)
                if found:
                    rows.extend(found)
                    break
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
