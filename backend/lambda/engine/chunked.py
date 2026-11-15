"""A job cursor that survives the Lambda time limit."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Callable

import store
import timeutil

LEASE = timedelta(minutes=16)
_STOP_WITH_MS_LEFT = 120_000
_STATE_SK = "STATE"

Process = Callable[[Any], None]
Clock = Callable[[], datetime]
Invoker = Callable[[str], None]


class Busy(Exception):
    """Another run still holds the lease."""


def _pk(job: str) -> str:
    return f"JOB#{job}"


def _claim(job: str, now: datetime) -> bool:
    now_s = timeutil.format_iso_millis(now)
    lease = timeutil.format_iso_millis(now + LEASE)
    return store.update_conditional(
        _pk(job),
        _STATE_SK,
        "SET #status = :running, leaseUntil = :lease, updatedAt = :now",
        {":running": "running", ":lease": lease, ":now": now_s},
        "attribute_not_exists(leaseUntil) OR leaseUntil < :now",
        {"#status": "status"},
    )


def _save(job: str, status: str, cursor: int, total: int, now: datetime, lease: datetime | None) -> None:
    item: dict[str, Any] = {
        "pk": _pk(job),
        "sk": _STATE_SK,
        "status": status,
        "cursor": cursor,
        "total": total,
        "updatedAt": timeutil.format_iso_millis(now),
    }
    if lease is not None:
        item["leaseUntil"] = timeutil.format_iso_millis(lease)
    store.put(item)


def run(
    job: str,
    items: list[Any],
    process: Process,
    context: Any,
    *,
    now: Clock = timeutil.utc_now,
) -> dict[str, Any]:
    """Claim the job, process from the cursor, and stop with two minutes left."""
    moment = now()
    state = store.get(_pk(job), _STATE_SK) or {}
    if not _claim(job, moment):
        raise Busy(job)
    cursor = 0 if state.get("status") == "done" else int(state.get("cursor") or 0)
    total = len(items)
    lease = moment + LEASE
    try:
        while cursor < total:
            remaining = context.get_remaining_time_in_millis()
            if remaining < _STOP_WITH_MS_LEFT:
                _save(job, "running", cursor, total, now(), None)
                return {"status": "running", "cursor": cursor, "total": total}
            process(items[cursor])
            cursor += 1
            _save(job, "running", cursor, total, now(), lease)
        _save(job, "done", cursor, total, now(), None)
        return {"status": "done", "cursor": cursor, "total": total}
    except Exception:
        _save(job, "failed", cursor, total, now(), None)
        raise


def resume_stalled(
    *,
    now: Clock = timeutil.utc_now,
    invoke: Invoker | None = None,
) -> list[str]:
    """Start again every running job whose lease has expired."""
    moment = timeutil.format_iso_millis(now())
    send = invoke or _invoke_self
    started: list[str] = []
    for item in store.scan_pk_prefix("JOB#"):
        if item.get("sk") != _STATE_SK or item.get("status") != "running":
            continue
        lease = str(item.get("leaseUntil") or "")
        if lease and lease >= moment:
            continue
        job = str(item.get("pk") or "")[len("JOB#") :]
        if not job:
            continue
        send(job)
        started.append(job)
    return started


def _invoke_self(job: str) -> None:
    name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "")
    if not name:
        return
    import boto3

    boto3.client("lambda").invoke(
        FunctionName=name,
        InvocationType="Event",
        Payload=_payload(job),
    )


def _payload(job: str) -> bytes:
    import json

    return json.dumps({"job": job}).encode("utf-8")
