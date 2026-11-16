"""Read the stored prices and write one backtest's files."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import backtest
import config
import methodology
import s3io
import screen


def month_ends(register: dict[str, Any]) -> list[str]:
    """Month-end sessions from the monthly table, starting at the register's first month."""
    if not _ready_bucket():
        return []
    first = str(register["backtest"]["firstScreenMonth"])
    ends: list[str] = []
    for key in s3io.list_keys(config.data_bucket_name(), "prices/monthly/month="):
        month = key.split("month=", 1)[1][:7]
        if month < first:
            continue
        for row in s3io.get_jsonl_gz(config.data_bucket_name(), key):
            if isinstance(row, dict) and row.get("monthEnd"):
                ends.append(str(row["monthEnd"]))
                break
    return sorted(set(ends))


def parts() -> list[str]:
    if not _ready_bucket():
        return []
    keys = s3io.list_keys(config.data_bucket_name(), "prices/adj/")
    return sorted({key.split("part=", 1)[1][:3] for key in keys if "part=" in key and key.endswith("bars.jsonl.gz")})


def perform(item: tuple[str, str], identity: str, size: int, register: dict[str, Any]) -> None:
    kind, key = item
    bucket = config.data_bucket_name()
    if kind == "part":
        s3io.put_jsonl_gz(bucket, f"backtests/{identity}/factors/part={key}.jsonl.gz", _part_rows(key, register))
        return
    if kind == "month":
        payload = _holdings(identity, key, size, register)
        s3io.put_json(bucket, f"backtests/{identity}/holdings/month={key[:7]}.json", payload)
        return
    payload = _equity(identity, size, register)
    s3io.put_json(bucket, f"backtests/{identity}/equity.json", payload)
    _save_index(identity, size, register, payload)


def _part_rows(part: str, register: dict[str, Any]) -> list[dict[str, Any]]:
    bucket = config.data_bucket_name()
    key = f"prices/adj/part={part}/bars.jsonl.gz"
    if not s3io.exists(bucket, key):
        return []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in s3io.get_jsonl_gz(bucket, key):
        if isinstance(row, dict) and row.get("symbol"):
            grouped.setdefault(str(row["symbol"]), []).append(row)
    ends = month_ends(register)
    members = _members()
    sessions = _sessions()
    rows: list[dict[str, Any]] = []
    for symbol, bars in grouped.items():
        member = members.get(symbol) or {"symbol": symbol}
        close = backtest._number(member.get("close"))
        cap = backtest._number(member.get("marketCap"))
        shares = None if close in (None, 0) or cap is None else cap / close
        rows.extend(
            backtest.rows_for_symbol(
                symbol,
                ends,
                _pit(str(member.get("cik") or "")),
                bars,
                close,
                shares,
                sessions,
                register,
                sector=str(member.get("sector") or ""),
                sic=member.get("sic"),
                median_dollar_volume=backtest._number(member.get("medianDollarVolume")),
            )
        )
    return rows


def _holdings(identity: str, month_end: str, size: int, register: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for row in _factor_rows(identity)
        if str(row.get("monthEnd") or "") == month_end and backtest.eligible(row, register["universe"])
    ]
    ranked = sorted(screen.score(rows, register), key=backtest._rank_key)
    chosen = backtest.choose(ranked, size, int(register["backtest"]["maxNamesPerSector"]))
    return {
        "month": month_end[:7],
        "monthEnd": month_end,
        "registerHash": methodology.register_hash(register),
        "portfolioSize": size,
        "holdings": [
            {"symbol": row["symbol"], "sector": row.get("sector"), "weight": row["weight"], "rank": row.get("rank")}
            for row in chosen
        ],
    }


def _equity(identity: str, size: int, register: dict[str, Any]) -> dict[str, Any]:
    holdings = _saved_holdings(identity)
    ends = sorted(holdings)
    symbols = {str(row.get("symbol")) for rows in holdings.values() for row in rows}
    symbols.update({str(register["backtest"]["benchmark"]), str(register["backtest"]["cashProxy"])})
    played = backtest.replay(
        ends,
        {},
        _price_book(symbols),
        _sessions(),
        register,
        portfolio_size=size,
        holdings_by_month=holdings,
    )
    played["registerHash"] = methodology.register_hash(register)
    played["portfolioSize"] = size
    return played


def _factor_rows(identity: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prefix = f"backtests/{identity}/factors/"
    for key in s3io.list_keys(config.data_bucket_name(), prefix):
        rows.extend(row for row in s3io.get_jsonl_gz(config.data_bucket_name(), key) if isinstance(row, dict))
    return rows


def _save_index(identity: str, size: int, register: dict[str, Any], payload: dict[str, Any]) -> None:
    import store

    store.put(
        _decimals(
            {
                "pk": f"BACKTEST#{identity}",
                "sk": "META",
                "gsi1pk": "BACKTESTS",
                "gsi1sk": identity,
                "runId": identity,
                "portfolioSize": size,
                "registerHash": methodology.register_hash(register),
                "lastPriceCount": int(payload.get("lastPriceCount") or 0),
            }
        )
    )


def _saved_holdings(identity: str) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    for key in s3io.list_keys(config.data_bucket_name(), f"backtests/{identity}/holdings/"):
        payload = s3io.get_json(config.data_bucket_name(), key)
        if isinstance(payload, dict):
            found[str(payload.get("monthEnd") or payload.get("month") or "")] = list(payload.get("holdings") or [])
    return found


def _price_book(symbols: set[str]) -> dict[str, list[dict[str, Any]]]:
    book: dict[str, dict[str, dict[str, Any]]] = {symbol: {} for symbol in symbols}
    bucket = config.data_bucket_name()
    for kind, field in (("adj", "adj"), ("split", "split")):
        for key in s3io.list_keys(bucket, f"prices/{kind}/"):
            if not key.endswith("bars.jsonl.gz"):
                continue
            for row in s3io.get_jsonl_gz(bucket, key):
                symbol = str(row.get("symbol") or "") if isinstance(row, dict) else ""
                if symbol not in book:
                    continue
                day = str(row.get("date") or "")
                book[symbol].setdefault(day, {"date": day})[field] = row.get("close")
    return {
        symbol: [bar for _day, bar in sorted(days.items()) if "adj" in bar and "split" in bar]
        for symbol, days in book.items()
    }


def _members() -> dict[str, dict[str, Any]]:
    bucket = config.data_bucket_name()
    dates = [
        key.split("date=", 1)[1][:10] for key in s3io.list_keys(bucket, "universe/date=") if "/members.jsonl.gz" in key
    ]
    if not dates:
        return {}
    latest = max(dates)
    return {
        str(row.get("symbol")): row
        for row in s3io.get_jsonl_gz(bucket, f"universe/date={latest}/members.jsonl.gz")
        if isinstance(row, dict) and row.get("symbol")
    }


def _pit(cik: str) -> list[dict[str, Any]]:
    if not cik:
        return []
    key = f"fundamentals/pit/cik={cik}/facts.jsonl.gz"
    bucket = config.data_bucket_name()
    if not s3io.exists(bucket, key):
        return []
    return [row for row in s3io.get_jsonl_gz(bucket, key) if isinstance(row, dict)]


def _sessions() -> list[str]:
    found: list[str] = []
    bucket = config.data_bucket_name()
    for key in s3io.list_keys(bucket, "reference/calendar/"):
        payload = s3io.get_json(bucket, key)
        if isinstance(payload, dict):
            found.extend(str(day) for day in payload.get("sessions") or [])
    return sorted(set(found))


def _decimals(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _decimals(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimals(item) for item in value]
    return value


def _ready_bucket() -> bool:
    return bool(os.environ.get("DATA_BUCKET_NAME"))
