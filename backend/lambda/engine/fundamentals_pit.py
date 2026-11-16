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


def _role_facts(company_facts: dict[str, Any], tags: list[str]) -> list[dict[str, Any]]:
    """Every filing of these tags. ``rank`` is the tag preference, lower first."""
    found: list[dict[str, Any]] = []
    for rank, tag in enumerate(tags):
        for row in _fact_rows(company_facts, "longTermDebt", tag, "stock"):
            item = dict(row)
            item["rank"] = rank
            found.append(item)
    return found


def _visible_fact(facts: list[dict[str, Any]], end: str, filed: str) -> dict[str, Any] | None:
    """The preferred tag's latest filing on or before ``filed`` for this balance-sheet date."""
    visible = [row for row in facts if row["end"] == end and row["filed"] <= filed]
    if not visible:
        return None
    best = min(int(row["rank"]) for row in visible)
    chosen = [row for row in visible if int(row["rank"]) == best]
    return max(chosen, key=lambda row: str(row["filed"]))


def _combine_debt(
    noncurrent: float | None,
    including: float | None,
    portion: float | None,
    current: float | None,
    borrowings: float | None,
) -> tuple[float | None, float | None]:
    """Split one balance sheet without counting the same dollars twice.

    ``LongTermDebt`` includes its current portion. ``DebtCurrent`` includes
    that portion and short-term borrowings. When only those two totals exist,
    the smaller one is treated as sitting inside the larger one, so the
    current line is kept and the total is the larger figure. Borrowings that
    sit in ``DebtCurrent`` and were never inside ``LongTermDebt`` are missed.
    Counting both totals would count the current portion twice. A missing role
    stays missing here. The snapshot turns an unreported debt tag into zero.
    """
    implied = (
        including - noncurrent if noncurrent is not None and including is not None and including >= noncurrent else None
    )
    if noncurrent is not None:
        long_term: float | None = noncurrent
    elif including is not None and portion is not None and including >= portion:
        long_term = including - portion
    elif including is not None and current is not None and portion is None:
        long_term = including - current if including >= current else 0
    elif including is not None:
        long_term = including
    else:
        long_term = None
    if current is not None:
        short_term: float | None = current
    elif portion is not None or implied is not None or borrowings is not None:
        short_term = float(portion if portion is not None else implied or 0) + float(borrowings or 0)
    else:
        short_term = None
    return long_term, short_term


def _debt_rows(company_facts: dict[str, Any], roles: dict[str, list[str]]) -> list[dict[str, Any]]:
    """One debt row per balance-sheet date and filing date.

    A later filing that repeats an old column does not replace the original
    filing date. ``as_of`` then sees the value that was public on that day,
    and a restatement only after it was filed.
    """
    facts = {role: _role_facts(company_facts, tags) for role, tags in roles.items()}
    ends = {row["end"] for rows in facts.values() for row in rows}
    emitted: list[dict[str, Any]] = []
    for end in ends:
        filed_dates = sorted({row["filed"] for rows in facts.values() for row in rows if row["end"] == end})
        for filed in filed_dates:
            chosen = {role: _visible_fact(rows, end, filed) for role, rows in facts.items()}
            long_term, short_term = _combine_debt(
                _amount(chosen.get("noncurrent")),
                _amount(chosen.get("includingCurrent")),
                _amount(chosen.get("currentPortion")),
                _amount(chosen.get("debtCurrent")),
                _amount(chosen.get("borrowings")),
            )
            stamp = next((row for row in chosen.values() if row is not None and row["filed"] == filed), None)
            if stamp is None:
                continue
            label = _joined_tag(chosen)
            if long_term is not None:
                emitted.append(_debt_row(stamp, end, filed, "longTermDebt", long_term, label))
            if short_term is not None:
                emitted.append(_debt_row(stamp, end, filed, "shortTermDebt", short_term, label))
    return emitted


def _joined_tag(chosen: dict[str, dict[str, Any] | None]) -> str:
    """Every tag that contributed, so a later reader can see the combination."""
    tags = sorted({str(row.get("tag") or "") for row in chosen.values() if isinstance(row, dict) and row.get("tag")})
    return "+".join(tags)


def _amount(row: dict[str, Any] | None) -> float | None:
    if row is None:
        return None
    return float(row["value"])


def _debt_row(stamp: dict[str, Any], end: str, filed: str, field: str, value: float, tag: str) -> dict[str, Any]:
    return {
        "field": field,
        "kind": "stock",
        "tag": tag,
        "start": end,
        "end": end,
        "value": value,
        "filed": filed,
        "form": stamp.get("form"),
        "fy": stamp.get("fy"),
        "fp": stamp.get("fp"),
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
