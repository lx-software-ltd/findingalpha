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
    """Flows, stocks, and share averages. Tag order is the preference order."""
    raw = json.loads((path or _CONTRACT).read_text(encoding="utf-8"))
    maps: TagMaps = {}
    for section in ("flows", "stocks", "shareFlows"):
        fields = raw.get(section)
        if not isinstance(fields, dict) or not fields:
            raise ValueError(f"fundamentals contract is missing {section}")
        maps[section] = {str(field): [str(tag) for tag in tags] for field, tags in fields.items()}
    debt = raw.get("debt")
    if isinstance(debt, dict) and debt:
        maps["debt"] = {str(role): [str(tag) for tag in tags] for role, tags in debt.items()}
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
    series = units.get("shares") if field == _SHARES_FIELD or kind == "share" else units.get("USD")
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
                "tag": tag,
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


def _preferred_by_end(company_facts: dict[str, Any], tags: list[str]) -> dict[str, dict[str, Any]]:
    """One stock fact per balance-sheet date. The earlier tag wins; a later filing of that tag replaces it."""
    best: dict[str, tuple[int, dict[str, Any]]] = {}
    for rank, tag in enumerate(tags):
        for row in _fact_rows(company_facts, "longTermDebt", tag, "stock"):
            current = best.get(row["end"])
            if current is None or rank < current[0] or (rank == current[0] and row["filed"] > current[1]["filed"]):
                best[row["end"]] = (rank, row)
    return {end: row for end, (_rank, row) in best.items()}


def _component(values: dict[str, dict[str, dict[str, Any]]], role: str, end: str) -> float | None:
    row = values.get(role, {}).get(end)
    if row is None:
        return None
    return float(row["value"])


def _debt_rows(company_facts: dict[str, Any], roles: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Split debt without counting the current portion twice.

    ``LongTermDebt`` already includes ``LongTermDebtCurrent``. ``DebtCurrent``
    already includes the current portion and short-term borrowings, so those
    are not added again. A missing role stays missing. It is not stored as zero.
    """
    values = {role: _preferred_by_end(company_facts, tags) for role, tags in roles.items()}
    ends: set[str] = set()
    for by_end in values.values():
        ends.update(by_end)
    rows: list[dict[str, Any]] = []
    for end in ends:
        noncurrent = _component(values, "noncurrent", end)
        including = _component(values, "includingCurrent", end)
        portion = _component(values, "currentPortion", end)
        current = _component(values, "debtCurrent", end)
        borrowings = _component(values, "borrowings", end)
        inclusive = noncurrent is None and including is not None
        long_term: float | None
        if noncurrent is not None:
            long_term = noncurrent
        elif inclusive and portion is not None and including is not None and including >= portion:
            long_term = including - portion
        elif inclusive:
            long_term = including
        else:
            long_term = None
        short_term: float | None
        if inclusive and portion is None:
            short_term = borrowings
        elif current is not None:
            short_term = current
        elif portion is not None or borrowings is not None:
            short_term = (portion or 0) + (borrowings or 0)
        else:
            short_term = None
        if long_term is not None:
            rows.append(_debt_row(values, end, "longTermDebt", long_term))
        if short_term is not None:
            rows.append(_debt_row(values, end, "shortTermDebt", short_term))
    return rows


def _debt_row(values: dict[str, dict[str, dict[str, Any]]], end: str, field: str, value: float) -> dict[str, Any]:
    used = [row for by_end in values.values() if (row := by_end.get(end)) is not None]
    latest = max(used, key=lambda row: row["filed"])
    return {
        "field": field,
        "kind": "stock",
        "tag": "+".join(sorted({str(row["tag"]) for row in used})),
        "start": end,
        "end": end,
        "value": value,
        "filed": latest["filed"],
        "form": latest["form"],
        "fy": latest.get("fy"),
        "fp": latest.get("fp"),
    }


def normalise(company_facts: dict[str, Any], maps: TagMaps | None = None) -> list[dict[str, Any]]:
    """Turn a companyfacts payload into rows.

    USD only, except share counts. 10-K, 10-Q and their amendments only.
    For each period, the first tag that has a value wins. A later tag
    still fills periods the earlier tags do not cover.

    Long-term and short-term debt are the exception. The ``debt`` roles
    are combined per balance-sheet date so the current portion is not
    added twice and short-term borrowings are not dropped.
    """
    chosen = maps if maps is not None else load_tag_maps()
    rows: list[dict[str, Any]] = []
    skip: set[str] = set()
    if chosen.get("debt"):
        rows.extend(_debt_rows(company_facts, chosen["debt"]))
        skip = {"longTermDebt", "shortTermDebt"}
    for kind, section in (("flow", "flows"), ("stock", "stocks"), ("share", "shareFlows")):
        for field, tags in (chosen.get(section) or {}).items():
            if field in skip:
                continue
            best: dict[tuple[str, str], tuple[int, list[dict[str, Any]]]] = {}
            for rank, tag in enumerate(tags):
                grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
                for row in _fact_rows(company_facts, field, tag, kind):
                    grouped.setdefault((row["start"], row["end"]), []).append(row)
                for key, group in grouped.items():
                    current = best.get(key)
                    if current is None or rank < current[0]:
                        best[key] = (rank, group)
            for _rank, group in best.values():
                rows.extend(group)
    return rows


def as_of(rows: list[dict[str, Any]], on: str) -> list[dict[str, Any]]:
    """Rows filed on or before ``on``. One row per field and period: the latest filing.

    Share counts filed together are added, so two classes become one total.
    The same count repeated in that filing is kept once. A later filing
    replaces the total. A weighted-average share count is not added to
    another duration.
    """
    chosen: dict[tuple[str, str, str], dict[str, Any]] = {}
    shares: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row["filed"] > on:
            continue
        if row.get("field") == _SHARES_FIELD:
            shares.setdefault((str(row["start"]), str(row["end"])), []).append(row)
            continue
        if row.get("kind") == "share":
            key = (row["field"], row["start"], row["end"])
            current = chosen.get(key)
            if current is None or row["filed"] > current["filed"]:
                chosen[key] = row
            continue
        key = (row["field"], row["start"], row["end"])
        current = chosen.get(key)
        if current is None or row["filed"] > current["filed"]:
            chosen[key] = row
    for key, group in shares.items():
        combined = _combine_shares(group)
        if combined is not None:
            chosen[(_SHARES_FIELD, key[0], key[1])] = combined
    return list(chosen.values())


def _combine_shares(group: list[dict[str, Any]]) -> dict[str, Any] | None:
    latest = max(str(row["filed"]) for row in group)
    same = [row for row in group if str(row["filed"]) == latest]
    values: list[float] = []
    for row in same:
        raw = row.get("value")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        number = float(raw)
        if number not in values:
            values.append(number)
    if not values:
        return None
    base = dict(same[0])
    base["value"] = sum(values)
    base["tag"] = same[0].get("tag")
    return base


def _class_of(row: dict[str, Any]) -> str | None:
    return period_class(_as_date(row["start"]) or date.min, _as_date(row["end"]) or date.min)


def _year_to_date(row: dict[str, Any], fy_end: date) -> bool:
    """A year-to-date value starts when the new fiscal year starts, not mid-year."""
    start = _as_date(row["start"])
    if start is None or _class_of(row) == "year":
        return False
    return abs((start - (fy_end + timedelta(days=1))).days) <= 10


def ttm(rows_as_of: list[dict[str, Any]], field: str) -> float | None:
    """Trailing twelve months: FY + YTD - YTD_prev, or FY when no later year-to-date exists."""
    flows = [row for row in rows_as_of if row["field"] == field and row["kind"] == "flow"]
    annual = [row for row in flows if _class_of(row) == "year"]
    if not annual:
        return None
    fy = max(annual, key=lambda row: row["end"])
    fy_end = _as_date(fy["end"])
    assert fy_end is not None
    later = [row for row in flows if row["end"] > fy["end"] and _year_to_date(row, fy_end)]
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
