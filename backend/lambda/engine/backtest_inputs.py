"""Point-in-time inputs for one backtest run. Each function reads the bucket once per call."""

from __future__ import annotations

from datetime import date
from typing import Any

import config
import market_files
import s3io


def action_years(month_ends: list[str]) -> list[str]:
    """Calendar years that can hold a split before the last month end, from 2015."""
    if not month_ends:
        return []
    first = max(int(month_ends[0][:4]) - 1, 2015)
    last = int(month_ends[-1][:4])
    return [str(year) for year in range(first, last + 1)]


def write_actions(year: str, identity: str, *, bucket: str | None = None, client: Any = None) -> None:
    """Splits in ``year``, keyed by symbol, for the share-count adjustment."""
    name = _bucket(bucket)
    grouped: dict[str, list[list[object]]] = {}
    for key in s3io.list_keys(name, f"corporate-actions/date={year}-", client=client):
        for row in s3io.get_jsonl_gz(name, key, client=client):
            parsed = market_files.split_ratio(row) if isinstance(row, dict) else None
            if parsed is None:
                continue
            symbol, ex, ratio = parsed
            grouped.setdefault(symbol, []).append([ex, ratio])
    s3io.put_json(name, f"backtests/{identity}/actions/{year}.json", grouped, client=client)


def saved_splits(identity: str, *, bucket: str | None = None, client: Any = None) -> dict[str, list[tuple[str, float]]]:
    """Splits written by :func:`write_actions`."""
    name = _bucket(bucket)
    found: dict[str, list[tuple[str, float]]] = {}
    prefix = f"backtests/{identity}/actions/"
    for key in s3io.list_keys(name, prefix, client=client):
        payload = s3io.get_json(name, key, client=client)
        if not isinstance(payload, dict):
            continue
        for symbol, events in payload.items():
            if not isinstance(events, list):
                continue
            for item in events:
                if isinstance(item, list) and len(item) == 2:
                    found.setdefault(str(symbol), []).append((str(item[0]), float(item[1])))
    return found


def identities(
    bucket: str | None = None, client: Any = None, *, tickers: dict[str, Any] | None = None
) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """Every universe file, oldest first. A name that later drops out keeps its last row.

    A symbol that was never in a universe file takes today's CIK when ``tickers``
    has one. Its sector stays blank.
    """
    name = _bucket(bucket)
    dates = sorted(
        {
            key.split("date=", 1)[1][:10]
            for key in s3io.list_keys(name, "universe/date=", client=client)
            if "/members.jsonl.gz" in key
        }
    )
    table: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for day in dates:
        for row in s3io.get_jsonl_gz(name, f"universe/date={day}/members.jsonl.gz", client=client):
            if not isinstance(row, dict) or not row.get("symbol"):
                continue
            symbol = str(row["symbol"])
            table.setdefault(symbol, []).append((day, _who(row, symbol)))
    for symbol, entry in (tickers or {}).items():
        if symbol in table or not isinstance(entry, dict):
            continue
        cik = str(entry.get("cik") or "").strip()
        if not cik.isdigit():
            continue
        table[symbol] = [
            ("0001-01-01", {"cik": cik.zfill(10), "sector": "", "sic": None, "name": str(entry.get("name") or symbol)})
        ]
    return table


def identity_on(table: dict[str, list[tuple[str, dict[str, Any]]]], symbol: str, day: str) -> dict[str, Any]:
    """The latest membership on or before ``day``. The earliest row is used when none is yet public."""
    rows = table.get(symbol) or []
    if not rows:
        return {"cik": "", "sector": "", "sic": None, "name": symbol}
    prior = [item for item in rows if item[0] <= day]
    return dict(prior[-1][1] if prior else rows[0][1])


def monthly_for(
    symbols: set[str], bucket: str | None = None, client: Any = None
) -> dict[str, dict[str, dict[str, Any]]]:
    """``symbol -> month -> {close, medianDollarVolume}`` from the monthly table."""
    name = _bucket(bucket)
    found: dict[str, dict[str, dict[str, Any]]] = {symbol: {} for symbol in symbols}
    if not found:
        return found
    for key in s3io.list_keys(name, "prices/monthly/month=", client=client):
        month = key.split("month=", 1)[1][:7]
        for row in s3io.get_jsonl_gz(name, key, client=client):
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "")
            if symbol not in found:
                continue
            found[symbol][month] = {
                "close": row.get("close"),
                "medianDollarVolume": row.get("medianDollarVolume"),
            }
    return found


def shares_on(pit: list[dict[str, Any]], splits: list[tuple[str, float]], end: str) -> float | None:
    """Split-adjusted shares public on ``end``. Missing or stale filings stay missing."""
    import share_count

    events: list[tuple[date, float]] = []
    for ex, ratio in splits:
        try:
            events.append((date.fromisoformat(str(ex)[:10]), float(ratio)))
        except ValueError:
            continue
    try:
        day = date.fromisoformat(end[:10])
    except ValueError:
        return None
    import fundamentals_pit

    visible = fundamentals_pit.as_of(pit, end[:10]) if pit else []
    chosen = share_count.shares_as_of(visible, events, day)
    if chosen is None:
        return None
    return float(chosen["shares"])


def factor_rows(identity: str, month: str, bucket: str | None = None, client: Any = None) -> list[dict[str, Any]]:
    """Factor rows for one month. Other months stay unread."""
    name = _bucket(bucket)
    rows: list[dict[str, Any]] = []
    prefix = f"backtests/{identity}/factors/month={month}/"
    for key in s3io.list_keys(name, prefix, client=client):
        rows.extend(row for row in s3io.get_jsonl_gz(name, key, client=client) if isinstance(row, dict))
    return rows


def held_symbols(identity: str, *, bucket: str | None = None, client: Any = None) -> set[str]:
    """Symbols that appear in any saved monthly portfolio."""
    name = _bucket(bucket)
    found: set[str] = set()
    for key in s3io.list_keys(name, f"backtests/{identity}/holdings/", client=client):
        payload = s3io.get_json(name, key, client=client)
        if not isinstance(payload, dict):
            continue
        for row in payload.get("holdings") or []:
            if isinstance(row, dict) and row.get("symbol"):
                found.add(str(row["symbol"]))
    return found


def write_marks(
    part: str, identity: str, register: dict[str, Any], *, bucket: str | None = None, client: Any = None
) -> None:
    """Daily adjusted and split closes for names this run held, plus the two benchmarks."""
    name = _bucket(bucket)
    needed = held_symbols(identity, bucket=name, client=client)
    needed.update({str(register["backtest"]["benchmark"]), str(register["backtest"]["cashProxy"])})
    joined: dict[str, dict[str, dict[str, Any]]] = {}
    for kind, field in (("adj", "adj"), ("split", "split")):
        key = f"prices/{kind}/part={part}/bars.jsonl.gz"
        if not s3io.exists(name, key, client=client):
            continue
        for row in s3io.get_jsonl_gz(name, key, client=client):
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "")
            if symbol not in needed:
                continue
            day = str(row.get("date") or "")
            joined.setdefault(symbol, {}).setdefault(day, {"symbol": symbol, "date": day})[field] = row.get("close")
    rows = [bar for days in joined.values() for bar in days.values() if "adj" in bar and "split" in bar]
    s3io.put_jsonl_gz(name, f"backtests/{identity}/marks/part={part}.jsonl.gz", rows, client=client)


def price_book(
    identity: str, symbols: set[str], *, bucket: str | None = None, client: Any = None
) -> dict[str, list[dict[str, Any]]]:
    """The mark files for ``symbols``. The full price parts are not read again."""
    name = _bucket(bucket)
    book: dict[str, dict[str, dict[str, Any]]] = {symbol: {} for symbol in symbols}
    for key in s3io.list_keys(name, f"backtests/{identity}/marks/", client=client):
        for row in s3io.get_jsonl_gz(name, key, client=client):
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "")
            if symbol not in book or "adj" not in row or "split" not in row:
                continue
            book[symbol][str(row.get("date") or "")] = {
                "date": row.get("date"),
                "adj": row.get("adj"),
                "split": row.get("split"),
            }
    return {symbol: [bar for _day, bar in sorted(days.items())] for symbol, days in book.items()}


def _who(row: dict[str, Any], symbol: str) -> dict[str, Any]:
    return {
        "cik": str(row.get("cik") or ""),
        "sector": str(row.get("sector") or ""),
        "sic": row.get("sic"),
        "name": str(row.get("name") or symbol),
    }


def _bucket(bucket: str | None) -> str:
    return bucket or config.data_bucket_name()
