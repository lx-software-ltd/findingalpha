"""Switches, the broker mode, and the latest job runs."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from config import env_flag
from http_common import _json_response
from kill_switch import is_enabled
from settings import SWITCHES, _flags, _row

_JOBS = Path(__file__).resolve().parent / "contracts" / "jobs.json"


def _jobs() -> list[dict[str, Any]]:
    payload = json.loads(_JOBS.read_text(encoding="utf-8"))
    jobs = payload.get("jobs", payload)
    return list(jobs) if isinstance(jobs, list) else []


def _schedule(job: dict[str, Any]) -> str:
    rate = str(job.get("rate") or "")
    if rate:
        return f"rate({rate})"
    cron = str(job.get("cron") or "")
    zone = str(job.get("timeZone") or "")
    return f"{cron} {zone}".strip()


def _duration_ms(item: dict[str, Any]) -> int:
    start = str(item.get("sk", "")).removeprefix("RUN#")
    finished = str(item.get("finishedAt") or "")
    if not start or not finished:
        return 0
    try:
        began = datetime.fromisoformat(start.replace("Z", "+00:00"))
        ended = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, int((ended - began).total_seconds() * 1000))


def _last_run(job: str) -> dict[str, Any] | None:
    import store

    rows = store.query_latest(f"JOB#{job}", "RUN#", 1)
    if not rows:
        return None
    item = rows[0]
    return {
        "status": item.get("status", ""),
        "startedAt": str(item.get("sk", "")).removeprefix("RUN#"),
        "durationMs": _duration_ms(item),
        "message": str(item.get("errorMessage") or ""),
    }


def status(_event: dict[str, Any]) -> dict[str, Any]:
    row = _row()
    flags = _flags(row)
    switches = [
        {
            "name": name,
            "parameter": env_flag(_env(name), default=False),
            "setting": flags[name],
            "effective": is_enabled(name, row),
        }
        for name in SWITCHES
    ]
    import jobs_handler

    runnable = {name for name in (str(job.get("name") or "") for job in _jobs()) if jobs_handler.handler_for(name)}
    jobs = [
        {
            "job": job["name"],
            "schedule": _schedule(job),
            "manualRun": job.get("manualRun") is True and str(job.get("name")) in runnable,
            "keyRun": job.get("keyRun") is True,
            "progress": _progress(str(job["name"])),
            "lastRun": _last_run(str(job["name"])),
        }
        for job in _jobs()
    ]
    return _json_response(
        200,
        {"switches": switches, "brokerMode": os.environ.get("BROKER_MODE", "paper"), "jobs": jobs},
    )


def _progress(job: str) -> dict[str, Any] | None:
    import store

    item = store.get(f"JOB#{job}", "STATE") or {}
    cursor = _count(item.get("cursor"))
    total = _count(item.get("total"))
    if cursor is None or total is None:
        return None
    return {"status": str(item.get("status") or ""), "cursor": cursor, "total": total}


def _count(value: object) -> int | None:
    from decimal import Decimal

    if type(value) is int:
        return value
    if isinstance(value, Decimal) and value == int(value):
        return int(value)
    return None


def _env(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def list_runs(event: dict[str, Any]) -> dict[str, Any]:
    import store

    raw = (event.get("queryStringParameters") or {}).get("limit") or "50"
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return _json_response(400, {"message": "limit must be an integer"})
    if limit < 1 or limit > 100:
        return _json_response(400, {"message": "limit must be from 1 to 100"})
    rows = store.query_gsi1_latest("JOBRUNS", limit)
    runs = [
        {
            "job": item.get("job", ""),
            "status": item.get("status", ""),
            "startedAt": item.get("gsi1sk") or str(item.get("sk", "")).removeprefix("RUN#"),
            "durationMs": _duration_ms(item),
            "message": str(item.get("errorMessage") or ""),
        }
        for item in rows
    ]
    return _json_response(200, {"runs": runs})
