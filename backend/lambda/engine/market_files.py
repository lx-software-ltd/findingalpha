"""Read stored prices and splits once, then look up a symbol."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import s3io


def sessions(bucket: str, client: Any = None) -> list[str]:
    """Every stored session date."""
    found: list[str] = []
    for key in s3io.list_keys(bucket, "reference/calendar/", client=client):
        payload = s3io.get_json(bucket, key, client=client)
        if isinstance(payload, dict):
            found.extend(str(day) for day in payload.get("sessions") or [])
    return sorted(set(found))


def bars_by_symbol(bucket: str, client: Any = None, *, prefix: str = "prices/adj/") -> dict[str, list[dict[str, Any]]]:
    """Adjusted bars grouped by symbol. Each part file is read once."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for key in s3io.list_keys(bucket, prefix, client=client):
        if not key.endswith("bars.jsonl.gz"):
            continue
        for row in s3io.get_jsonl_gz(bucket, key, client=client):
            if isinstance(row, dict) and row.get("symbol"):
                grouped.setdefault(str(row["symbol"]), []).append(row)
    return grouped


def raw_closes(bucket: str, day: str, sessions_on: list[str], client: Any = None) -> dict[str, float]:
    """Close on the last session on or before ``day``. One raw file."""
    prior = [item for item in sessions_on if item <= day]
    if not prior:
        return {}
    key = f"prices/raw/date={prior[-1]}/bars.jsonl.gz"
    if not s3io.exists(bucket, key, client=client):
        return {}
    closes: dict[str, float] = {}
    for row in s3io.get_jsonl_gz(bucket, key, client=client):
        if not isinstance(row, dict) or not row.get("symbol"):
            continue
        close = _number(row.get("close"))
        if close is not None:
            closes[str(row["symbol"])] = close
    return closes


def splits_until(
    bucket: str, day: str, client: Any = None, *, lookback_days: int = 500
) -> dict[str, list[tuple[str, float]]]:
    """Split ratios with an ex-date in the ``lookback_days`` before ``day``."""
    start = (date.fromisoformat(day) - timedelta(days=lookback_days)).isoformat()
    found: dict[str, list[tuple[str, float]]] = {}
    for key in s3io.list_keys(bucket, "corporate-actions/date=", client=client):
        stamp = key.split("date=", 1)[1][:10]
        if stamp < start or stamp > day:
            continue
        for row in s3io.get_jsonl_gz(bucket, key, client=client):
            parsed = split_ratio(row) if isinstance(row, dict) else None
            if parsed is None:
                continue
            symbol, ex, ratio = parsed
            found.setdefault(symbol, []).append((ex, ratio))
    return found


def split_ratio(row: dict[str, Any]) -> tuple[str, str, float] | None:
    """``(symbol, ex-date, splitTo / splitFrom)`` when the row is a split."""
    symbol = str(row.get("symbol") or "")
    ex = str(row.get("exDate") or "")[:10]
    old = _number(row.get("splitFrom"))
    new = _number(row.get("splitTo"))
    if not symbol or len(ex) != 10 or old is None or new is None or old <= 0 or new <= 0:
        return None
    return symbol, ex, new / old


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
