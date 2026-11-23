"""Read the stored prices and write one backtest's files."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import backtest
import backtest_inputs
import config
import methodology
import s3io
import screen


def month_ends(register: dict[str, Any], *, bucket: str | None = None, client: Any = None) -> list[str]:
    """Month-end sessions from the monthly table, starting at the register's first month."""
    if bucket is None and not _ready_bucket():
        return []
    name = bucket or config.data_bucket_name()
    first = str(register["backtest"]["firstScreenMonth"])
    ends: list[str] = []
    for key in s3io.list_keys(name, "prices/monthly/month=", client=client):
        month = key.split("month=", 1)[1][:7]
        if month < first:
            continue
        for row in s3io.get_jsonl_gz(name, key, client=client):
            if isinstance(row, dict) and row.get("monthEnd"):
                ends.append(str(row["monthEnd"]))
                break
    found = sorted(set(ends))
    import market_files

    sessions = market_files.sessions(name, client)
    return backtest.complete_month_ends(found, sessions) if sessions else found


def parts() -> list[str]:
    if not _ready_bucket():
        return []
    keys = s3io.list_keys(config.data_bucket_name(), "prices/adj/")
    return sorted({key.split("part=", 1)[1][:3] for key in keys if "part=" in key and key.endswith("bars.jsonl.gz")})


def perform(
    item: tuple[str, str],
    identity: str,
    size: int,
    register: dict[str, Any],
    *,
    bucket: str | None = None,
    client: Any = None,
) -> None:
    kind, key = item
    name = bucket or config.data_bucket_name()
    if kind == "inputs":
        backtest_inputs.write_inputs(identity, bucket=name, client=client)
        return
    if kind == "actions":
        backtest_inputs.write_actions(key, identity, bucket=name, client=client)
        return
    if kind == "part":
        _part_rows(key, identity, register, bucket=name, client=client)
        return
    if kind == "month":
        payload = _holdings(identity, key, size, register)
        s3io.put_json(name, f"backtests/{identity}/holdings/month={key[:7]}.json", payload, client=client)
        return
    if kind == "marks":
        backtest_inputs.write_marks(key, identity, register, bucket=name, client=client)
        return
    payload = _equity(identity, size, register)
    s3io.put_json(name, f"backtests/{identity}/equity.json", payload, client=client)
    _save_index(identity, size, register, payload)


def _part_rows(
    part: str,
    identity: str,
    register: dict[str, Any],
    *,
    bucket: str | None = None,
    client: Any = None,
    sic_of: Any = None,
) -> None:
    name = bucket or config.data_bucket_name()
    key = f"prices/adj/part={part}/bars.jsonl.gz"
    if not s3io.exists(name, key, client=client):
        return
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in s3io.get_jsonl_gz(name, key, client=client):
        if isinstance(row, dict) and row.get("symbol"):
            grouped.setdefault(str(row["symbol"]), []).append(row)
    ends = month_ends(register, bucket=name, client=client)
    anchor = ends[-1] if ends else "9999-12-31"
    tickers, reused, table = backtest_inputs.read_inputs(identity, bucket=name, client=client)
    stats = backtest_inputs.monthly_for(set(grouped), name, client)
    splits = backtest_inputs.saved_splits(identity, bucket=name, client=client)
    sessions = _sessions(name, client)
    sic_cache: dict[str, str | None] = {}
    lookup = sic_of or (lambda cik: backtest_inputs.cached_sic(name, cik, sic_cache, client))
    covers: dict[str, Any] = {}
    written: dict[str, list[dict[str, Any]]] = {}
    for symbol, bars in grouped.items():
        if symbol in table:
            who = backtest_inputs.identity_on(table, symbol, anchor)
        else:
            who = backtest_inputs.widen_one(symbol, tickers, reused, lookup)
        if symbol not in table and not who.get("cik"):
            continue
        pit = _pit(str(who.get("cik") or ""), bucket=name, client=client)
        symbol_splits = splits.get(symbol) or []
        company = str(who.get("cik") or "")

        def shares_on(
            end: str,
            pit: list[dict[str, Any]] = pit,
            symbol_splits: list[tuple[str, float]] = symbol_splits,
            company: str = company,
        ) -> float | None:
            return backtest_inputs.shares_on(
                pit,
                symbol_splits,
                end,
                cover=backtest_inputs.cached_cover(name, company, end, covers, client),
            )

        rows = backtest.rows_for_symbol(
            symbol,
            ends,
            pit,
            bars,
            None,
            None,
            sessions,
            register,
            sector=str(who.get("sector") or ""),
            sic=who.get("sic"),
            by_month=stats.get(symbol) or {},
            shares_on=shares_on,
        )
        for row in rows:
            row["name"] = who.get("name") or symbol
            written.setdefault(str(row["month"]), []).append(row)
    for month, group in written.items():
        s3io.put_jsonl_gz(
            name, f"backtests/{identity}/factors/month={month}/part={part}.jsonl.gz", group, client=client
        )


def _holdings(identity: str, month_end: str, size: int, register: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for row in backtest_inputs.factor_rows(identity, month_end[:7])
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
    ends = sorted(day for day in holdings if day)
    symbols = {str(row.get("symbol")) for rows in holdings.values() for row in rows}
    symbols.update({str(register["backtest"]["benchmark"]), str(register["backtest"]["cashProxy"])})
    played = backtest.replay(
        ends,
        {},
        backtest_inputs.price_book(identity, symbols),
        _sessions(),
        register,
        portfolio_size=size,
        holdings_by_month=holdings,
    )
    played["registerHash"] = methodology.register_hash(register)
    played["portfolioSize"] = size
    return played


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
                "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "done",
                "lastPriceCount": int(payload.get("lastPriceCount") or 0),
                "unpricedCount": int(payload.get("unpricedCount") or 0),
                "missingBenchmarkCount": int(payload.get("missingBenchmarkCount") or 0),
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


def _pit(cik: str, *, bucket: str | None = None, client: Any = None) -> list[dict[str, Any]]:
    if not cik:
        return []
    name = bucket or config.data_bucket_name()
    key = f"fundamentals/pit/cik={cik}/facts.jsonl.gz"
    if not s3io.exists(name, key, client=client):
        return []
    return [row for row in s3io.get_jsonl_gz(name, key, client=client) if isinstance(row, dict)]


def _sessions(bucket: str | None = None, client: Any = None) -> list[str]:
    if bucket is None and not _ready_bucket():
        return []
    import market_files

    return market_files.sessions(bucket or config.data_bucket_name(), client)


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
