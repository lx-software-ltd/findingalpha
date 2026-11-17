"""A job cursor that survives the Lambda time limit."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

import store
import timeutil

logger = logging.getLogger(__name__)

LEASE = timedelta(minutes=16)
_STOP_WITH_MS_LEFT = 120_000
_STATE_SK = "STATE"
_GSI_PK = "JOBSTATE"
_MAX_FAILURES = 3
_PAYLOAD_MAX = 200_000

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
        "SET #status = :running, leaseUntil = :lease, updatedAt = :now, gsi1pk = :gsi1pk, gsi1sk = :gsi1sk",
        {":running": "running", ":lease": lease, ":now": now_s, ":gsi1pk": _GSI_PK, ":gsi1sk": job},
        "attribute_not_exists(leaseUntil) OR leaseUntil < :now",
        {"#status": "status"},
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    raise TypeError(type(value).__name__)


def _digest(items: list[Any]) -> str:
    raw = json.dumps(items, default=_json_ready, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _save(
    job: str,
    status: str,
    cursor: int,
    total: int,
    now: datetime,
    lease: datetime | None,
    digest: str,
    params: dict[str, Any] | None,
    failures: int = 0,
) -> None:
    item: dict[str, Any] = {
        "pk": _pk(job),
        "sk": _STATE_SK,
        "status": status,
        "cursor": cursor,
        "total": total,
        "itemsDigest": digest,
        "updatedAt": timeutil.format_iso_millis(now),
        "gsi1pk": _GSI_PK,
        "gsi1sk": job,
        "failures": failures,
    }
    if failures:
        item["failedCursor"] = cursor
    if lease is not None:
        item["leaseUntil"] = timeutil.format_iso_millis(lease)
    if params is not None:
        item["params"] = params
    store.put(item)


def run(
    job: str,
    items: list[Any],
    process: Process,
    context: Any,
    *,
    now: Clock = timeutil.utc_now,
    params: dict[str, Any] | None = None,
    enabled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Claim the job, process from the cursor, and stop with two minutes left.

    A saved digest that does not match ``items`` starts again at the
    first item. A row with no digest keeps its cursor.
    """
    moment = now()
    try:
        previous = _claim(job, moment) or {}
    except store.ConditionNotMet:
        raise Busy(job) from None
    digest = _digest(items)
    cursor = 0 if previous.get("status") == "done" else int(previous.get("cursor") or 0)
    saved = previous.get("itemsDigest")
    if saved is not None and saved != digest:
        cursor = 0
    total = len(items)
    lease = moment + LEASE
    try:
        while cursor < total:
            if enabled is not None and not enabled():
                _save(job, "paused", cursor, total, now(), None, digest, params)
                return {"status": "paused", "cursor": cursor, "total": total}
            remaining = context.get_remaining_time_in_millis()
            if remaining < _STOP_WITH_MS_LEFT:
                _save(job, "running", cursor, total, now(), None, digest, params)
                return {"status": "running", "cursor": cursor, "total": total}
            process(items[cursor])
            cursor += 1
            _save(job, "running", cursor, total, now(), lease, digest, params)
        _save(job, "done", cursor, total, now(), None, digest, params)
        return {"status": "done", "cursor": cursor, "total": total}
    except Exception:
        count = int(previous.get("failures") or 0)
        if previous.get("failedCursor") != cursor:
            count = 0
        _save(job, "failed", cursor, total, now(), None, digest, params, failures=count + 1)
        raise


def resume_stalled(
    *,
    now: Clock = timeutil.utc_now,
    invoke: Invoker | None = None,
    enabled: Callable[[str], bool] | None = None,
) -> list[str]:
    """Start a job that should continue, when ``enabled`` allows it.

    A running job whose lease expired, a paused job, and a failed job
    that carries a failure count under three. A failed row with no count
    waits for Run now.
    """
    moment = timeutil.format_iso_millis(now())
    send = invoke or _invoke_self
    started: list[str] = []
    failed: list[dict[str, str]] = []
    for item in store.query_gsi1(_GSI_PK):
        if item.get("sk") != _STATE_SK or not _resumable(item, moment):
            continue
        job = str(item.get("gsi1sk") or "")
        if not job or (enabled is not None and not enabled(job)):
            continue
        try:
            send(job)
        except Exception as exc:
            logger.error("resume invoke failed job=%s error=%s", job, type(exc).__name__)
            failed.append({"job": job, "error": type(exc).__name__})
            continue
        started.append(job)
    return {"started": started, "failed": failed}


def _resumable(item: dict[str, Any], moment: str) -> bool:
    status = item.get("status")
    if status == "failed":
        # A count is written by run(). A row marked failed without one, such as a
        # universe build, would otherwise restart on every tick.
        if "failures" not in item:
            return False
        return int(item["failures"]) < _MAX_FAILURES
    if status == "paused":
        return True
    if status != "running":
        return False
    lease = str(item.get("leaseUntil") or "")
    return not lease or lease < moment


def _invoke_self(job: str) -> None:
    name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "")
    if not name:
        return
    import boto3

    item = store.get(_pk(job), _STATE_SK) or {}
    boto3.client("lambda").invoke(
        FunctionName=name,
        InvocationType="Event",
        Payload=_payload(job, item.get("params")),
    )


def _whole_number(value: Any) -> int:
    """DynamoDB returns a whole number as Decimal. The resumed job expects an int."""
    if isinstance(value, Decimal):
        try:
            if value.is_finite() and value == value.to_integral_value():
                return int(value)
        except (ArithmeticError, ValueError):
            pass
    raise TypeError(type(value).__name__)


def _payload(job: str, params: object) -> bytes:
    """The resume event. A parameter block over 200 KB stays in the state row."""
    body: dict[str, object] = {"job": job}
    if not params:
        return json.dumps(body).encode("utf-8")
    encoded = json.dumps({"job": job, "params": params}, default=_whole_number).encode("utf-8")
    if len(encoded) <= _PAYLOAD_MAX:
        return encoded
    body["paramsInState"] = True
    return json.dumps(body).encode("utf-8")
