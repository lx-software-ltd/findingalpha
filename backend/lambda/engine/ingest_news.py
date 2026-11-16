"""Headlines for the names we hold or shortlist.

The article body is not stored. The same story is written once per
symbol, under the New York date of ``createdAt``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

import config
import s3io

_NEW_YORK = ZoneInfo("America/New_York")
News = Callable[[list[str], str, str], list[dict[str, Any]]]


class IngestDisabled(Exception):
    """``IngestEnabled`` is off, so no request was sent."""


def _require(check: Callable[[], bool] | None) -> None:
    allowed = check if check is not None else _default_ingest
    if not allowed():
        raise IngestDisabled()


def _default_ingest() -> bool:
    import kill_switch

    return kill_switch.is_enabled("ingestEnabled")


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _z(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _bounds(end: date) -> tuple[str, str]:
    start = datetime(end.year, end.month, end.day, tzinfo=_NEW_YORK) - timedelta(days=2)
    finish = datetime(end.year, end.month, end.day, tzinfo=_NEW_YORK) + timedelta(days=1)
    return _z(start), _z(finish)


def _news_day(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(_NEW_YORK).date().isoformat()


def _default_news(symbols: list[str], start: str, end: str) -> list[dict[str, Any]]:
    import alpaca_data

    return alpaca_data.news(symbols, start, end)


def daily(
    symbols: list[str],
    end: date | datetime | str,
    *,
    fetch_news: News | None = None,
    bucket: str | None = None,
    client: Any = None,
    ingest_enabled: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """The last three New York dates, ending on ``end``. Empty symbols fetch nothing."""
    clean = sorted({str(symbol).strip() for symbol in symbols if str(symbol).strip()})
    if not clean:
        return {"items": 0}
    _require(ingest_enabled)
    last = _as_date(end)
    days = [(last - timedelta(days=offset)).isoformat() for offset in (2, 1, 0)]
    news_of = fetch_news or _default_news
    start, finish = _bounds(last)
    seen: set[object] = set()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in news_of(clean, start, finish):
        story_id = row.get("id")
        if story_id in seen:
            continue
        seen.add(story_id)
        day = _news_day(row.get("createdAt"))
        if day not in days:
            continue
        for symbol in row.get("symbols") or []:
            if symbol in clean:
                grouped.setdefault((symbol, day), []).append(row)
    name = bucket if bucket is not None else config.data_bucket_name()
    for symbol in clean:
        for day in days:
            rows = sorted(grouped.get((symbol, day), []), key=lambda item: str(item.get("id")))
            s3io.put_jsonl_gz(name, f"news/symbol={symbol}/date={day}.jsonl.gz", rows, client=client)
    filed = {row.get("id") for rows in grouped.values() for row in rows}
    return {"items": len(filed)}
