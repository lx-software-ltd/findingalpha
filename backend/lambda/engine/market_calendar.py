"""Trading sessions, cached one year at a time in the data bucket."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

import config
import s3io
import timeutil

NEW_YORK = ZoneInfo("America/New_York")
_CURRENT_YEAR_TTL = timedelta(days=1)
FetchYear = Callable[[int], list[str]]


def _key(year: int) -> str:
    return f"reference/calendar/year={year}.json"


def _parse(values: object) -> list[date]:
    if not isinstance(values, list):
        return []
    return [date.fromisoformat(str(value)) for value in values]


def _fresh(payload: dict[str, Any], now: datetime) -> bool:
    raw = payload.get("fetchedAt")
    if not isinstance(raw, str):
        return False
    try:
        fetched = timeutil.parse_iso_strict(raw)
    except ValueError:
        return False
    return now - fetched < _CURRENT_YEAR_TTL


def _load_year(year: int, fetch_year: FetchYear, *, client: Any, now: datetime, today: date) -> list[date]:
    bucket = config.data_bucket_name()
    key = _key(year)
    cached: dict[str, Any] | None = None
    if s3io.exists(bucket, key, client=client):
        loaded = s3io.get_json(bucket, key, client=client)
        cached = loaded if isinstance(loaded, dict) else None
    stored = _parse((cached or {}).get("sessions"))
    current = year == today.year
    if stored and not current:
        return stored
    if stored and current and cached is not None and _fresh(cached, now):
        return stored
    fresh = _parse(list(fetch_year(year)))
    if not fresh:
        return stored or fresh
    s3io.put_json(
        bucket,
        key,
        {"sessions": [day.isoformat() for day in fresh], "fetchedAt": timeutil.format_iso_millis(now)},
        client=client,
    )
    return fresh


def sessions(
    start: date,
    end: date,
    fetch_year: FetchYear,
    *,
    client: Any = None,
    now: datetime | None = None,
) -> list[date]:
    """Sessions from ``start`` through ``end``, inclusive."""
    moment = now or timeutil.utc_now()
    today = moment.astimezone(NEW_YORK).date()
    found: list[date] = []
    for year in range(start.year, end.year + 1):
        found.extend(
            day for day in _load_year(year, fetch_year, client=client, now=moment, today=today) if start <= day <= end
        )
    return found


def previous_session(
    today_new_york: date,
    fetch_year: FetchYear,
    *,
    client: Any = None,
    now: datetime | None = None,
) -> date | None:
    """The session strictly before ``today_new_york``."""
    days = sessions(date(today_new_york.year - 1, 1, 1), today_new_york, fetch_year, client=client, now=now)
    earlier = [day for day in days if day < today_new_york]
    return earlier[-1] if earlier else None


def new_york_today(now: datetime | None = None) -> date:
    moment = now or datetime.now(NEW_YORK)
    return moment.astimezone(NEW_YORK).date()


def fetch_alpaca_year(year: int) -> list[str]:
    """Session dates for one calendar year from the Alpaca trading calendar."""
    import alpaca_data

    client = alpaca_data._open()
    payload = client._json(
        alpaca_data._url(
            f"{alpaca_data._PAPER}/v2/calendar",
            {"start": f"{year}-01-01", "end": f"{year}-12-31"},
        )
    )
    if not isinstance(payload, list):
        raise ValueError("calendar response is not a list")
    return [str(row["date"])[:10] for row in payload if isinstance(row, dict) and row.get("date")]
