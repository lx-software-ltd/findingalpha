"""Month-end close and median dollar volume, built once for the backtest."""

from __future__ import annotations

import statistics
from datetime import date
from typing import Any

import config
import s3io

_START = "2016-03"


def month_rows(days: list[tuple[str, list[dict[str, Any]]]], month: str) -> list[dict[str, Any]]:
    """Close and median dollar volume for symbols that printed on the month's last session.

    ``days`` is ``(session, bars)`` and must cover that session and the 60
    sessions ending on it. Dollar volume is close times volume.
    """
    ordered = sorted(days, key=lambda item: item[0])
    in_month = [day for day, _bars in ordered if day[:7] == month]
    if not in_month:
        return []
    end = in_month[-1]
    window = [(day, bars) for day, bars in ordered if day <= end][-60:]
    end_bars = {str(bar.get("symbol") or ""): bar for bar in window[-1][1] if bar.get("symbol")}
    volumes_by_symbol = _volumes_by_symbol(window)
    rows: list[dict[str, Any]] = []
    for symbol, bar in sorted(end_bars.items()):
        close = _number(bar.get("close"))
        volumes = volumes_by_symbol.get(symbol) or []
        if close is None or not volumes:
            continue
        rows.append(
            {
                "symbol": symbol,
                "monthEnd": end,
                "close": close,
                "medianDollarVolume": statistics.median(volumes),
            }
        )
    return rows


def for_adjusted(
    members: list[str],
    tickers: dict[str, Any],
    *,
    rows: list[dict[str, Any]] | None = None,
    client: Any = None,
) -> list[str]:
    """Members, plus names that cleared the price and volume floors and still have a CIK.

    The floor check starts at the register's first screen month. A name with no
    current CIK, including a delisted ticker, is left out.
    """
    import methodology

    register = methodology.load()
    since = str(register["backtest"]["firstScreenMonth"])
    rules = register["universe"]
    found = rows if rows is not None else _rows_since(since, client)
    qualified = _symbols_meeting(found, since, float(rules["minPriceUsd"]), float(rules["minMedianDollarVolumeUsd"]))
    covered = {symbol for symbol in qualified if _has_cik(tickers.get(symbol))}
    return sorted({str(symbol) for symbol in members if str(symbol)} | covered)


def months_to_refresh(months: list[str]) -> list[str]:
    """The newest month and the one before it.

    A run during the current month writes a file whose last session is not
    the month end. The next run rewrites that file as well as the new month.
    """
    if not months:
        return []
    return months[-2:]


def months_between(start: str, end: str) -> list[str]:
    """``YYYY-MM`` from ``start`` through ``end``, inclusive."""
    cursor = date(int(start[:4]), int(start[5:7]), 1)
    stop = date(int(end[:4]), int(end[5:7]), 1)
    found: list[str] = []
    while cursor <= stop:
        found.append(f"{cursor.year:04d}-{cursor.month:02d}")
        year = cursor.year + (1 if cursor.month == 12 else 0)
        month = 1 if cursor.month == 12 else cursor.month + 1
        cursor = date(year, month, 1)
    return found


def run(
    event: dict[str, Any],
    context: Any = None,
    *,
    months: list[str] | None = None,
    read: Any = None,
    write: Any = None,
    client: Any = None,
) -> dict[str, Any]:
    """One month per chunk, from 2016-03 through the latest raw session."""
    import chunked

    chosen = months if months is not None else _listed_months(client)
    if not chosen:
        return {"ok": False, "status": "missing_inputs"}
    reader = read or (lambda month: _window(month, client))
    writer = write or (lambda month, rows: _store(month, rows, client))

    def process(month: str) -> None:
        writer(month, month_rows(reader(month), month))

    result = chunked.run(
        "backfill_monthly_stats", chosen, process, context, params={"start": chosen[0]}, enabled=_ingest_enabled
    )
    return {"ok": True, **result}


def _ingest_enabled() -> bool:
    import kill_switch

    return kill_switch.is_enabled("ingestEnabled")


def append_latest(event: dict[str, Any], _context: Any = None, *, client: Any = None) -> dict[str, Any]:
    """Rewrite the newest month and the one before it. The weekly refresh calls this."""
    del event
    if not _bucket_ready():
        return {"ok": False, "status": "missing_inputs"}
    chosen = _listed_months(client)
    if not chosen:
        return {"ok": False, "status": "missing_inputs"}
    written: list[str] = []
    symbols = 0
    for month in months_to_refresh(chosen):
        rows = month_rows(_window(month, client), month)
        if not rows:
            continue
        _store(month, rows, client)
        written.append(month)
        symbols = len(rows)
    if not written:
        return {"ok": False, "status": "missing_inputs"}
    return {"ok": True, "status": "done", "month": written[-1], "months": written, "symbols": symbols}


def _symbols_meeting(rows: list[dict[str, Any]], since: str, min_price: float, min_volume: float) -> set[str]:
    found: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        month = str(row.get("monthEnd") or "")[:7]
        symbol = str(row.get("symbol") or "")
        close = _number(row.get("close"))
        volume = _number(row.get("medianDollarVolume"))
        if month < since or not symbol or close is None or volume is None:
            continue
        if close >= min_price and volume >= min_volume:
            found.add(symbol)
    return found


def _has_cik(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    text = str(entry.get("cik") or "").strip()
    return text.isdigit() and int(text) > 0


def _rows_since(since: str, client: Any) -> list[dict[str, Any]]:
    if not _bucket_ready():
        return []
    bucket = config.data_bucket_name()
    found: list[dict[str, Any]] = []
    for key in s3io.list_keys(bucket, "prices/monthly/month=", client=client):
        month = key.split("month=", 1)[1][:7]
        if month < since:
            continue
        found.extend(row for row in s3io.get_jsonl_gz(bucket, key, client=client) if isinstance(row, dict))
    return found


def _bucket_ready() -> bool:
    import os

    return bool(os.environ.get("DATA_BUCKET_NAME"))


def _volumes_by_symbol(window: list[tuple[str, list[dict[str, Any]]]]) -> dict[str, list[float]]:
    """Dollar volume for every symbol, in one pass over the window."""
    found: dict[str, list[float]] = {}
    for _day, bars in window:
        for bar in bars:
            symbol = str(bar.get("symbol") or "")
            close = _number(bar.get("close"))
            volume = _number(bar.get("volume"))
            if not symbol or close is None or volume is None:
                continue
            found.setdefault(symbol, []).append(close * volume)
    return found


def _listed_months(client: Any) -> list[str]:
    if not _bucket_ready():
        return []
    bucket = config.data_bucket_name()
    days = sorted(
        key.split("date=", 1)[1][:10]
        for key in s3io.list_keys(bucket, "prices/raw/date=", client=client)
        if "date=" in key
    )
    if not days:
        return []
    return [month for month in months_between(_START, days[-1][:7]) if any(day.startswith(month) for day in days)]


def _window(month: str, client: Any) -> list[tuple[str, list[dict[str, Any]]]]:
    bucket = config.data_bucket_name()
    days = sorted(
        key.split("date=", 1)[1][:10]
        for key in s3io.list_keys(bucket, "prices/raw/date=", client=client)
        if "date=" in key
    )
    in_month = [day for day in days if day.startswith(month)]
    if not in_month:
        return []
    end = in_month[-1]
    chosen = [day for day in days if day <= end][-60:]
    loaded: list[tuple[str, list[dict[str, Any]]]] = []
    for day in chosen:
        loaded.append(
            (
                day,
                [
                    row
                    for row in s3io.get_jsonl_gz(bucket, f"prices/raw/date={day}/bars.jsonl.gz", client=client)
                    if isinstance(row, dict)
                ],
            )
        )
    return loaded


def _store(month: str, rows: list[dict[str, Any]], client: Any) -> None:
    s3io.put_jsonl_gz(
        config.data_bucket_name(),
        f"prices/monthly/month={month}/stats.jsonl.gz",
        rows,
        client=client,
    )


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
