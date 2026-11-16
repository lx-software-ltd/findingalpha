"""One share count for a market cap, and the splits that apply to it.

A cover-page count is current on its ``end`` date. A balance-sheet
count is restated when the filing is prepared, so splits count from
``filed``. A weighted average is used only when both are missing or
older than 450 days, and a cover page that companyfacts dropped is
the last source.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, NamedTuple

MAX_AGE_DAYS = 450
COVER_TAG = "dei:EntityCommonStockSharesOutstanding"
_COVER_NAME = "dei:EntityCommonStockSharesOutstanding"
_FACT = re.compile(r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", re.IGNORECASE | re.DOTALL)
_ATTR = re.compile(r"""([:\w.-]+)(?:=(?:"([^"]*)"|'([^']*)'))?""")
_CONTEXT = re.compile(
    r"""<xbrli:context\b[^>]*\bid=["']([^"']+)["'][^>]*>(.*?)</xbrli:context>""",
    re.IGNORECASE | re.DOTALL,
)
_INSTANT = re.compile(r"<xbrli:instant>\s*([^<]+?)\s*</xbrli:instant>", re.IGNORECASE)


class Chosen(NamedTuple):
    """An unadjusted count, the date splits are counted from, and its source."""

    value: float
    end: date
    after: date
    source: str


def split_factor(splits: list[Any], after: date, through: date) -> float:
    """Product of ``splitTo / splitFrom`` for ``after < exDate <= through``."""
    factor = 1.0
    for item in splits:
        ex, ratio = _split(item)
        if ex is None or ratio is None:
            continue
        if after < ex <= through:
            factor *= ratio
    return factor


def choose(rows: list[dict[str, Any]], on: date, *, max_age: int = MAX_AGE_DAYS) -> Chosen | None:
    """The fresh outstanding count, or the latest diluted average when it is not."""
    outstanding = _fresh(rows, "sharesOutstanding", on, max_age)
    if outstanding:
        row = _latest_end(outstanding)
        value = _positive(row.get("value"))
        if value is not None:
            end = _day(row.get("end"))
            filed = _day(row.get("filed")) or end
            if end is not None and filed is not None:
                cover = str(row.get("tag") or "") == COVER_TAG
                return Chosen(value, end, end if cover else filed, "cover" if cover else "balanceSheet")
    weighted = _fresh(rows, "weightedDilutedShares", on, max_age)
    if not weighted:
        return None
    latest_end = max(str(row.get("end")) for row in weighted)
    at_end = [row for row in weighted if str(row.get("end")) == latest_end]
    row = max(at_end, key=lambda item: (str(item.get("start") or ""), str(item.get("filed") or "")))
    value = _positive(row.get("value"))
    end = _day(row.get("end"))
    filed = _day(row.get("filed")) or end
    if value is None or end is None or filed is None:
        return None
    return Chosen(value, end, filed, "weightedDiluted")


def from_cover(cover: dict[str, Any] | None, on: date, *, max_age: int = MAX_AGE_DAYS) -> Chosen | None:
    """A class sum from a filing cover page. An empty or stale page is ``None``."""
    if not isinstance(cover, dict):
        return None
    value = _positive(cover.get("value"))
    end = _day(cover.get("end"))
    filed = _day(cover.get("filed"))
    if value is None or end is None or filed is None or filed > on:
        return None
    if (on - end).days > max_age:
        return None
    return Chosen(value, end, end, "coverClasses")


def shares_as_of(
    rows: list[dict[str, Any]],
    splits: list[Any],
    on: date,
    *,
    cover: dict[str, Any] | None = None,
    max_age: int = MAX_AGE_DAYS,
) -> dict[str, Any] | None:
    """Adjusted shares, the count date, the split date, and the source."""
    chosen = choose(rows, on, max_age=max_age) or from_cover(cover, on, max_age=max_age)
    if chosen is None:
        return None
    return {
        "shares": chosen.value * split_factor(splits, chosen.after, on),
        "end": chosen.end.isoformat(),
        "after": chosen.after.isoformat(),
        "source": chosen.source,
    }


def parse_cover_shares(document: str) -> dict[str, Any] | None:
    """Sum class counts on the latest cover instant. Preferred stock is ignored."""
    instants = _instants(document)
    by_context: dict[str, tuple[date, float]] = {}
    for attrs, text in _FACT.findall(document):
        fields = _attrs(attrs)
        if fields.get("name") != _COVER_NAME:
            continue
        context = fields.get("contextref") or fields.get("contextRef") or ""
        instant = instants.get(context)
        value = _scaled(text, fields.get("scale"))
        if not context or instant is None or value is None or value <= 0:
            continue
        by_context.setdefault(context, (instant, value))
    if not by_context:
        return None
    latest = max(instant for instant, _value in by_context.values())
    total = sum(value for instant, value in by_context.values() if instant == latest)
    if total <= 0:
        return None
    return {"end": latest.isoformat(), "value": total}


def _fresh(rows: list[dict[str, Any]], field: str, on: date, max_age: int) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for row in rows:
        if row.get("field") != field:
            continue
        end = _day(row.get("end"))
        if end is None or (on - end).days > max_age:
            continue
        kept.append(row)
    return kept


def _latest_end(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest = max(str(row.get("end")) for row in rows)
    at_end = [row for row in rows if str(row.get("end")) == latest]
    return max(at_end, key=lambda item: str(item.get("filed") or ""))


def _instants(document: str) -> dict[str, date]:
    found: dict[str, date] = {}
    for context, body in _CONTEXT.findall(document):
        match = _INSTANT.search(body)
        if match is None:
            continue
        instant = _day(match.group(1))
        if instant is not None:
            found[context] = instant
    return found


def _attrs(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for name, double, single in _ATTR.findall(text):
        found[name] = double if double else single
    return found


def _scaled(text: str, scale: str | None) -> float | None:
    cleaned = text.replace(",", "").replace("\xa0", "").strip()
    if not cleaned:
        return None
    try:
        value = float(cleaned)
        if scale:
            value *= 10 ** int(scale)
    except (TypeError, ValueError):
        return None
    return value


def _split(item: Any) -> tuple[date | None, float | None]:
    if isinstance(item, tuple) and len(item) == 2:
        ex = item[0] if isinstance(item[0], date) else _day(item[0])
        ratio = item[1] if isinstance(item[1], (int, float)) and not isinstance(item[1], bool) else None
        return ex, float(ratio) if ratio is not None and ratio > 0 else None
    if not isinstance(item, dict):
        return None, None
    old = _positive(item.get("splitFrom"))
    new = _positive(item.get("splitTo"))
    if old is None or new is None:
        return None, None
    return _day(item.get("exDate")), new / old


def _positive(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number <= 0:
        return None
    return number


def _day(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None
