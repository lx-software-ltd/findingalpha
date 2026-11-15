"""Trading sessions, cached one year at a time in the data bucket."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import config
import s3io

NEW_YORK = ZoneInfo("America/New_York")
FetchYear = Callable[[int], list[str]]


def _key(year: int) -> str:
    return f"reference/calendar/year={year}.json"


def _load_year(year: int, fetch_year: FetchYear, *, client: Any = None) -> list[date]:
    bucket = config.data_bucket_name()
    key = _key(year)
    if s3io.exists(bucket, key, client=client):
        payload = s3io.get_json(bucket, key, client=client)
    else:
        payload = {"sessions": list(fetch_year(year))}
        s3io.put_json(bucket, key, payload, client=client)
    return [date.fromisoformat(value) for value in payload.get("sessions") or []]


def sessions(
    start: date,
    end: date,
    fetch_year: FetchYear,
    *,
    client: Any = None,
) -> list[date]:
    """Sessions from ``start`` through ``end``, inclusive."""
    found: list[date] = []
    for year in range(start.year, end.year + 1):
        found.extend(day for day in _load_year(year, fetch_year, client=client) if start <= day <= end)
    return found


def previous_session(
    today_new_york: date,
    fetch_year: FetchYear,
    *,
    client: Any = None,
) -> date | None:
    """The session strictly before ``today_new_york``."""
    days = sessions(date(today_new_york.year - 1, 1, 1), today_new_york, fetch_year, client=client)
    earlier = [day for day in days if day < today_new_york]
    return earlier[-1] if earlier else None


def new_york_today(now: datetime | None = None) -> date:
    moment = now or datetime.now(NEW_YORK)
    return moment.astimezone(NEW_YORK).date()
