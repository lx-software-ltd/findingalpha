"""Raw prices, corporate actions, and the adjusted history.

Alpaca selects corporate actions by process date, and that date can be
in the future. The fetch window is seven days before the session
through 75 days after it. Rows are stored only when the ex-date is the
session. See ``docs/research/data-sources.md``.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Callable

import chunked
import config
import s3io
from alpaca_data import IngestDisabled, hold_ingest_check

LOOKBACK_DAYS = 7
LOOKAHEAD_DAYS = 75
_PART = 100
_EXCHANGES = frozenset({"NYSE", "NASDAQ"})
_BACKFILL_JOB = "backfill_prices"
_ADJUSTED_JOB = "refresh_adjusted"
_RAW = re.compile(r"^prices/raw/date=(\d{4}-\d{2}-\d{2})/bars\.jsonl\.gz$")
_PRICES = ("open", "high", "low", "close")
Bars = Callable[[list[str], date, date, str], Any]
Actions = Callable[[date, date], list[dict[str, Any]]]


class DataQualityError(Exception):
    """A session failed a check. Nothing for that session was written."""

    def __init__(self, check: str) -> None:
        super().__init__(check)
        self.check = check


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


def reused_symbols(assets: list[dict[str, Any]], *, include_inactive: bool) -> list[dict[str, Any]]:
    """Tickers that have more than one NYSE or NASDAQ asset."""
    statuses = {"active", "inactive"} if include_inactive else {"active"}
    grouped: dict[str, list[dict[str, str]]] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("exchange") not in _EXCHANGES or asset.get("status") not in statuses:
            continue
        symbol = str(asset.get("symbol") or "").strip()
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(
            {
                "id": str(asset.get("id") or ""),
                "status": str(asset.get("status") or ""),
                "exchange": str(asset.get("exchange")),
            }
        )
    return [{"symbol": symbol, "assets": rows} for symbol, rows in sorted(grouped.items()) if len(rows) > 1]


def _with_spy(symbols: list[str]) -> list[str]:
    found = {str(symbol).strip() for symbol in symbols if str(symbol).strip()}
    found.add("SPY")
    return sorted(found)


def raw_symbols(assets: list[dict[str, Any]], *, include_inactive: bool) -> list[str]:
    """NYSE and NASDAQ symbols, plus SPY.

    The daily job passes active assets. The backfill passes active and
    inactive assets together. SPY trades on ARCA, so it is added here.
    """
    statuses = {"active", "inactive"} if include_inactive else {"active"}
    found: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("exchange") not in _EXCHANGES or asset.get("status") not in statuses:
            continue
        symbol = str(asset.get("symbol") or "").strip()
        if symbol:
            found.append(symbol)
    return _with_spy(found)


def month_spans(start: date | str, end: date | str) -> list[tuple[date, date]]:
    """Calendar months clipped to the backfill range. One chunk each."""
    cursor = _as_date(start)
    last = _as_date(end)
    if last < cursor:
        return []
    spans: list[tuple[date, date]] = []
    while cursor <= last:
        nxt = date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(cursor.year, cursor.month + 1, 1)
        span_end = min(last, nxt - timedelta(days=1))
        spans.append((cursor, span_end))
        cursor = span_end + timedelta(days=1)
    return spans


def _raw_key(day: date) -> str:
    return f"prices/raw/date={day.isoformat()}/bars.jsonl.gz"


def _actions_key(day: date) -> str:
    return f"corporate-actions/date={day.isoformat()}/actions.jsonl.gz"


def _action_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (str(row.get("symbol")), str(row.get("type")), str(row.get("exDate")), str(row.get("processDate")))


def _bucket(bucket: str | None) -> str:
    return bucket if bucket is not None else config.data_bucket_name()


def _default_bars(symbols: list[str], start: date, end: date, adjustment: str) -> list[dict[str, Any]]:
    import alpaca_data

    return list(alpaca_data.daily_bars(symbols, start, end, adjustment))


def _default_actions(start: date, end: date) -> list[dict[str, Any]]:
    import alpaca_data

    return alpaca_data.corporate_actions(start, end)


def _previous_count(bucket: str, day: date, client: Any) -> int | None:
    prior: date | None = None
    for key in s3io.list_keys(bucket, "prices/raw/", client=client):
        match = _RAW.search(key)
        if match is None:
            continue
        found = date.fromisoformat(match.group(1))
        if found < day and (prior is None or found > prior):
            prior = found
    if prior is None:
        return None
    return sum(1 for _row in s3io.get_jsonl_gz(bucket, _raw_key(prior), client=client))


def _check(bars: list[dict[str, Any]], previous: int | None) -> None:
    if not any(isinstance(row, dict) and row.get("symbol") == "SPY" for row in bars):
        raise DataQualityError("spy_missing")
    for row in bars:
        if not isinstance(row, dict):
            raise DataQualityError("non_positive_price")
        for name in _PRICES:
            value = row.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise DataQualityError("non_positive_price")
    if previous is not None and abs(len(bars) - previous) * 100 > previous * 15:
        raise DataQualityError("bar_count")


def _put_day(bucket: str, day: date, bars: list[dict[str, Any]], actions: list[dict[str, Any]], client: Any) -> None:
    ordered = sorted(bars, key=lambda row: str(row.get("symbol")))
    kept = sorted(actions, key=_action_key)
    s3io.put_jsonl_gz(bucket, _raw_key(day), ordered, client=client)
    s3io.put_jsonl_gz(bucket, _actions_key(day), kept, client=client)


def _for_day(rows: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    token = day.isoformat()
    return [row for row in rows if row.get("exDate") == token]


def _hold(check: Callable[[], bool] | None) -> Any:
    _require(check)
    return hold_ingest_check()


_PART_KEY = re.compile(r"^prices/(?:adj|split)/part=(\d+)/bars\.jsonl\.gz$")


def _drop_stale_parts(bucket: str, count: int, client: Any) -> None:
    for prefix in ("prices/adj/", "prices/split/"):
        for key in s3io.list_keys(bucket, prefix, client=client):
            match = _PART_KEY.search(key)
            if match and int(match.group(1)) >= count:
                s3io.delete(bucket, key, client=client)
    s3io.put_json(bucket, "prices/manifest.json", {"parts": count}, client=client)


def ingest_raw_day(
    day: date | datetime | str,
    symbols: list[str],
    *,
    fetch_bars: Bars | None = None,
    fetch_actions: Actions | None = None,
    bucket: str | None = None,
    client: Any = None,
    ingest_enabled: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """Write one session. A failed check leaves both keys unwritten."""
    with _hold(ingest_enabled):
        return _ingest_raw_day(
            day, symbols, fetch_bars=fetch_bars, fetch_actions=fetch_actions, bucket=bucket, client=client
        )


def _ingest_raw_day(
    day: date | datetime | str,
    symbols: list[str],
    *,
    fetch_bars: Bars | None,
    fetch_actions: Actions | None,
    bucket: str | None,
    client: Any,
) -> dict[str, int]:
    session = _as_date(day)
    chosen = _with_spy(list(symbols))
    bars_of = fetch_bars or _default_bars
    actions_of = fetch_actions or _default_actions
    name = _bucket(bucket)
    bars = [row for row in bars_of(chosen, session, session, "raw") if row.get("date") == session.isoformat()]
    start = session - timedelta(days=LOOKBACK_DAYS)
    end = session + timedelta(days=LOOKAHEAD_DAYS)
    actions = _for_day(list(actions_of(start, end)), session)
    _check(bars, _previous_count(name, session, client))
    _put_day(name, session, bars, actions, client)
    return {"bars": len(bars), "actions": len(actions)}


def _write_month(
    span: tuple[date, date],
    sessions: list[date],
    symbols: list[str],
    bars_of: Bars,
    actions_of: Actions,
    bucket: str,
    client: Any,
) -> None:
    start, end = span
    days = [day for day in sessions if start <= day <= end]
    if not days:
        return
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in bars_of(symbols, start, end, "raw"):
        grouped.setdefault(str(row.get("date")), []).append(row)
    by_ex: dict[str, list[dict[str, Any]]] = {}
    window_start = start - timedelta(days=LOOKBACK_DAYS)
    window_end = end + timedelta(days=LOOKAHEAD_DAYS)
    for row in actions_of(window_start, window_end):
        by_ex.setdefault(str(row.get("exDate") or ""), []).append(row)
    previous = _previous_count(bucket, days[0], client)
    ready: list[tuple[date, list[dict[str, Any]], list[dict[str, Any]]]] = []
    for day in days:
        bars = grouped.get(day.isoformat(), [])
        actions = by_ex.get(day.isoformat(), [])
        _check(bars, previous)
        ready.append((day, bars, actions))
        previous = len(bars)
    for day, bars, actions in ready:
        _put_day(bucket, day, bars, actions, client)


def backfill_raw(
    start: date | str,
    end: date | str,
    sessions: list[date],
    context: Any,
    *,
    symbols: list[str],
    assets: list[dict[str, Any]] | None = None,
    fetch_bars: Bars | None = None,
    fetch_actions: Actions | None = None,
    bucket: str | None = None,
    client: Any = None,
    ingest_enabled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """One calendar month per chunk, including the inactive names in ``symbols``."""
    with _hold(ingest_enabled):
        return _backfill(
            start,
            end,
            sessions,
            context,
            symbols=symbols,
            assets=assets,
            fetch_bars=fetch_bars,
            fetch_actions=fetch_actions,
            bucket=bucket,
            client=client,
        )


def _backfill(
    start: date | str,
    end: date | str,
    sessions: list[date],
    context: Any,
    *,
    symbols: list[str],
    assets: list[dict[str, Any]] | None,
    fetch_bars: Bars | None,
    fetch_actions: Actions | None,
    bucket: str | None,
    client: Any,
) -> dict[str, Any]:
    chosen = _with_spy(list(symbols))
    bars_of = fetch_bars or _default_bars
    actions_of = fetch_actions or _default_actions
    name = _bucket(bucket)
    if assets is not None:
        s3io.put_json(name, "reference/symbol-reuse.json", reused_symbols(assets, include_inactive=True), client=client)
    spans = month_spans(start, end)

    def process(span: tuple[date, date]) -> None:
        _write_month(span, sessions, chosen, bars_of, actions_of, name, client)

    return chunked.run(
        _BACKFILL_JOB,
        spans,
        process,
        context,
        params={"start": _as_date(start).isoformat(), "end": _as_date(end).isoformat(), "symbols": chosen},
    )


def refresh_adjusted(
    symbols: list[str],
    start: date | str,
    end: date | str,
    context: Any,
    *,
    fetch_bars: Bars | None = None,
    bucket: str | None = None,
    client: Any = None,
    ingest_enabled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Full history in parts of 100. SPY and BIL are always included."""
    with _hold(ingest_enabled):
        return _refresh_adjusted(symbols, start, end, context, fetch_bars=fetch_bars, bucket=bucket, client=client)


def _refresh_adjusted(
    symbols: list[str],
    start: date | str,
    end: date | str,
    context: Any,
    *,
    fetch_bars: Bars | None,
    bucket: str | None,
    client: Any,
) -> dict[str, Any]:
    start_day = _as_date(start)
    end_day = _as_date(end)
    chosen = sorted(set(_with_spy(list(symbols))) | {"BIL"})
    bars_of = fetch_bars or _default_bars
    name = _bucket(bucket)
    parts = [(index, chosen[offset : offset + _PART]) for index, offset in enumerate(range(0, len(chosen), _PART))]

    def process(item: tuple[int, list[str]]) -> None:
        index, batch = item
        for adjustment, prefix in (("all", "adj"), ("split", "split")):
            rows = sorted(
                bars_of(batch, start_day, end_day, adjustment),
                key=lambda row: (str(row.get("date")), str(row.get("symbol"))),
            )
            s3io.put_jsonl_gz(name, f"prices/{prefix}/part={index:03d}/bars.jsonl.gz", rows, client=client)

    result = chunked.run(
        _ADJUSTED_JOB,
        parts,
        process,
        context,
        params={"start": start_day.isoformat(), "end": end_day.isoformat(), "symbols": chosen},
    )
    if result.get("status") == "done":
        _drop_stale_parts(name, len(parts), client)
    return result


def refresh_corporate_actions(
    start: date | str,
    end: date | str,
    sessions: list[date],
    *,
    fetch_actions: Actions | None = None,
    bucket: str | None = None,
    client: Any = None,
    ingest_enabled: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """Rewrite ex-date files. A row that appears after the daily run still lands."""
    with _hold(ingest_enabled):
        return _refresh_actions(start, end, sessions, fetch_actions=fetch_actions, bucket=bucket, client=client)


def _refresh_actions(
    start: date | str,
    end: date | str,
    sessions: list[date],
    *,
    fetch_actions: Actions | None,
    bucket: str | None,
    client: Any,
) -> dict[str, int]:
    first = _as_date(start)
    last = _as_date(end)
    days = [day for day in sessions if first <= day <= last]
    actions_of = fetch_actions or _default_actions
    by_ex: dict[str, list[dict[str, Any]]] = {}
    for row in actions_of(first - timedelta(days=LOOKBACK_DAYS), last + timedelta(days=LOOKAHEAD_DAYS)):
        by_ex.setdefault(str(row.get("exDate") or ""), []).append(row)
    name = _bucket(bucket)
    for day in days:
        kept = sorted(by_ex.get(day.isoformat(), []), key=_action_key)
        s3io.put_jsonl_gz(name, _actions_key(day), kept, client=client)
    return {"days": len(days)}
