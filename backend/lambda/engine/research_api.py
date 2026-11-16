"""Screen and backtest reads. The files hold the numbers. The index holds the dates."""

from __future__ import annotations

from typing import Any

import config
import s3io
from http_common import _json_response, not_found


def latest_screen(_event: dict[str, Any]) -> dict[str, Any]:
    import store

    rows = store.query_gsi1_latest("SCREENS", 1)
    if not rows:
        return not_found()
    return _screen(str(rows[0].get("asOf") or rows[0].get("gsi1sk") or ""))


def screen_by_date(event: dict[str, Any]) -> dict[str, Any]:
    parts = _path(event).strip("/").split("/")
    if len(parts) != 2:
        return not_found()
    return _screen(parts[1])


def list_backtests(_event: dict[str, Any]) -> dict[str, Any]:
    import store

    rows = store.query_gsi1("BACKTESTS")
    runs = [
        {
            "runId": item.get("runId"),
            "portfolioSize": _plain(item.get("portfolioSize")),
            "registerHash": item.get("registerHash"),
        }
        for item in sorted(rows, key=lambda item: str(item.get("gsi1sk") or ""), reverse=True)
        if item.get("sk") == "META"
    ]
    return _json_response(200, {"runs": runs})


def backtest_by_id(event: dict[str, Any]) -> dict[str, Any]:
    parts = _path(event).strip("/").split("/")
    if len(parts) != 2 or not parts[1]:
        return not_found()
    import store

    item = store.get(f"BACKTEST#{parts[1]}", "META")
    if not item:
        return not_found()
    key = f"backtests/{parts[1]}/equity.json"
    if not s3io.exists(config.data_bucket_name(), key):
        return not_found()
    payload = s3io.get_json(config.data_bucket_name(), key)
    if not isinstance(payload, dict):
        return not_found()
    payload["runId"] = parts[1]
    payload["portfolioSize"] = _plain(item.get("portfolioSize"))
    return _json_response(200, payload)


def _screen(day: str) -> dict[str, Any]:
    import store

    meta = store.get(f"SCREEN#{day}", "META")
    if not meta:
        return not_found()
    key = f"screens/date={day}/scores.jsonl.gz"
    if not s3io.exists(config.data_bucket_name(), key):
        return not_found()
    limit = int(meta.get("shortlistSize") or 0)
    rows = []
    for row in s3io.get_jsonl_gz(config.data_bucket_name(), key):
        rank = row.get("rank")
        if isinstance(rank, int) and not isinstance(rank, bool) and rank <= limit:
            rows.append(_public_row(row))
    rows.sort(key=lambda row: int(row["rank"]))
    counts = meta.get("counts") if isinstance(meta.get("counts"), dict) else {}
    return _json_response(
        200,
        {
            "asOf": day,
            "registerHash": meta.get("registerHash"),
            "counts": {name: _plain(counts.get(name)) for name in ("universe", "passed", "shortlisted")},
            "rows": rows,
        },
    )


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": row.get("rank"),
        "symbol": row.get("symbol"),
        "name": row.get("name") or row.get("symbol"),
        "sector": row.get("sector") or "",
        "composite": row.get("composite"),
        "groups": row.get("groups") or {},
        "factors": row.get("factors") or {},
        "z": row.get("z") or {},
    }


def _path(event: dict[str, Any]) -> str:
    return str((event.get("requestContext") or {}).get("http", {}).get("path") or "")


def _plain(value: object) -> object:
    if isinstance(value, bool) or value is None:
        return value
    if hasattr(value, "as_integer_ratio") and not isinstance(value, float):
        number = float(value)
        return int(number) if number.is_integer() else number
    return value
