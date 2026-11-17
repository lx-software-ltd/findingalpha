"""The universe build's job row and the adjusted refresh lease.

A second start does not run while the lease is still in the future. An
exception, and the third run left with an expired lease, mark the row failed
with no failure count, so tick waits for Run now.
"""

from __future__ import annotations

from datetime import date
from typing import Any

_HARD_STOPS = 3


def note_build(job: str, day: date, status: str, *, hard_stops: int | None = None) -> None:
    """Replace the build row. A failed row has no failure count and no lease."""
    import store
    import timeutil

    kept = status if status in {"running", "paused", "failed", "done"} else "failed"
    now = timeutil.utc_now()
    item: dict[str, Any] = {
        "pk": f"JOB#{job}",
        "sk": "STATE",
        "status": kept,
        "cursor": 0 if kept == "running" else 1,
        "total": 1,
        "gsi1pk": "JOBSTATE",
        "gsi1sk": job,
        "params": {"asOf": day.isoformat()},
        "updatedAt": timeutil.format_iso_millis(now),
    }
    if hard_stops is not None:
        item["hardStops"] = hard_stops
    store.put(item)


def claim_build(job: str, day: date) -> str:
    """Take the lease. ``busy`` and ``stopped`` mean the build must not start."""
    import chunked
    import store
    import timeutil

    now = timeutil.utc_now()
    now_s = timeutil.format_iso_millis(now)
    pk = f"JOB#{job}"
    current = store.get(pk, "STATE") or {}
    lease = str(current.get("leaseUntil") or "")
    running = current.get("status") == "running"
    if running and lease >= now_s:
        return "busy"
    stops = 0
    if running and lease and lease < now_s:
        stops = int(current.get("hardStops") or 0) + 1
        if stops >= _HARD_STOPS:
            note_build(job, day, "failed", hard_stops=stops)
            return "stopped"
    try:
        store.update_conditional(
            pk,
            "STATE",
            "SET #status = :running, leaseUntil = :lease, updatedAt = :now, "
            "gsi1pk = :gsi1pk, gsi1sk = :gsi1sk, #cursor = :cursor, #total = :total, "
            "params = :params, hardStops = :stops",
            {
                ":running": "running",
                ":lease": timeutil.format_iso_millis(now + chunked.LEASE),
                ":now": now_s,
                ":gsi1pk": "JOBSTATE",
                ":gsi1sk": job,
                ":cursor": 0,
                ":total": 1,
                ":params": {"asOf": day.isoformat()},
                ":stops": stops,
            },
            "attribute_not_exists(leaseUntil) OR leaseUntil < :now OR #status <> :running",
            {"#status": "status", "#cursor": "cursor", "#total": "total"},
        )
    except store.ConditionNotMet:
        return "busy"
    return "held"


def facts_open(job: str) -> bool:
    """The facts refresh is the job tick should resume, not a second build."""
    import store

    item = store.get(f"JOB#{job}", "STATE") or {}
    return item.get("status") in {"running", "paused"}


def save_adjusted(job: str, symbols: list[str], day: date, start: str, *, hold: bool) -> None:
    """Save the adjusted refresh before the coverage report.

    The lease keeps tick from starting a second copy. An empty list is kept
    because the refresh still writes SPY and BIL.
    """
    import chunked
    import store
    import timeutil

    now = timeutil.utc_now()
    item: dict[str, Any] = {
        "pk": f"JOB#{job}",
        "sk": "STATE",
        "status": "running",
        "cursor": 0,
        "total": 1,
        "gsi1pk": "JOBSTATE",
        "gsi1sk": job,
        "params": {"symbols": list(symbols), "start": start, "end": day.isoformat()},
        "updatedAt": timeutil.format_iso_millis(now),
    }
    if hold:
        item["leaseUntil"] = timeutil.format_iso_millis(now + chunked.LEASE)
    store.put(item)


def time_short(context: Any) -> bool:
    """True when less than two minutes remain."""
    import universe

    return universe._out_of_time(context)


def clear_progress(day: date) -> None:
    """Remove the progress file once the weekly tail has finished."""
    import os

    bucket = os.environ.get("DATA_BUCKET_NAME")
    if not bucket:
        return
    import universe_data

    universe_data.clear_build_progress(day, bucket, None)
