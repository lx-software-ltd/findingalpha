"""One row per job run, so the dashboard can show what ran."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Iterator

import timeutil
from http_common import _log_event
from storage_errors import STORAGE_ERRORS, error_code

RUN_TTL = timedelta(days=400)


class JobRun:
    def __init__(self, job: str, start: str) -> None:
        self.job = job
        self.start = start
        self.status = "running"
        self.error_class = ""
        self.error_message = ""

    def skip(self) -> None:
        self.status = "skipped_disabled"


def _expires_at() -> int:
    return int(timeutil.utc_now().timestamp()) + int(RUN_TTL.total_seconds())


def _write(run: JobRun) -> None:
    import store

    item: dict[str, Any] = {
        "pk": f"JOB#{run.job}",
        "sk": f"RUN#{run.start}",
        "gsi1pk": "JOBRUNS",
        "gsi1sk": run.start,
        "job": run.job,
        "status": run.status,
        "expiresAt": _expires_at(),
    }
    if run.error_class:
        item["errorClass"] = run.error_class
    if run.error_message:
        item["errorMessage"] = run.error_message[:300]
    if run.status != "running":
        item["finishedAt"] = timeutil.now_iso()
    store.put(item)


@contextmanager
def record(job: str) -> Iterator[JobRun]:
    start = timeutil.now_iso()
    run = JobRun(job, start)
    try:
        _write(run)
    except STORAGE_ERRORS as exc:
        _log_event("warning", tag="job_run_write_failed", job=job, error=error_code(exc))
    try:
        yield run
    except Exception as exc:
        run.status = "failed"
        run.error_class = type(exc).__name__
        run.error_message = str(exc)
        _safe_write(run)
        raise
    else:
        if run.status == "running":
            run.status = "succeeded"
        _safe_write(run)


def apply_result(run: JobRun, result: object) -> None:
    """A chunk that stopped is ``partial``. A refusal is ``failed``.

    ``running`` and ``paused`` mean the job continues on a later tick.
    ``missing_inputs`` and any other ``ok: false`` result are failures.
    A finished result stays for the recorder to mark ``succeeded``.
    """
    if run.status != "running" or not isinstance(result, dict):
        return
    status = str(result.get("status") or "")
    if status in {"running", "paused", "not_ready"}:
        run.status = "partial"
        if getattr(run, "job", "") == "kb_sync_check" and result.get("message") not in (None, "", "running"):
            run.error_message = str(result["message"])
        else:
            run.error_message = _partial_message(result)
        return
    if (
        getattr(run, "job", "") in {"kb_sync_check", "kb_eval"}
        and result.get("ok") is not False
        and status not in {"missing_inputs", "failed"}
    ):
        run.error_message = str(result.get("message") or status)
        return
    if status in {"missing_inputs", "failed"} or result.get("ok") is False:
        run.status = "failed"
        run.error_class = status or "failed"
        detail = result.get("error")
        if status == "missing_inputs":
            run.error_message = "missing inputs"
        elif isinstance(detail, str) and detail.strip():
            run.error_message = detail.strip()
        else:
            run.error_message = status or "failed"


def _partial_message(result: dict[str, Any]) -> str:
    cursor = _count(result.get("cursor"))
    total = _count(result.get("total"))
    if cursor is None or total is None:
        return "continues on the next tick"
    return f"{cursor} of {total}, continues on the next tick"


def position(item: dict[str, Any]) -> dict[str, Any] | None:
    """Cursor and total from a job state row, as plain integers."""
    cursor = _count(item.get("cursor"))
    total = _count(item.get("total"))
    if cursor is None or total is None:
        return None
    return {"status": str(item.get("status") or ""), "cursor": cursor, "total": total}


def positions() -> dict[str, dict[str, Any]]:
    """One read of every saved job position."""
    import store

    found: dict[str, dict[str, Any]] = {}
    for item in store.query_gsi1("JOBSTATE"):
        if item.get("sk") not in (None, "STATE"):
            continue
        name = str(item.get("gsi1sk") or "")
        placed = position(item)
        if name and placed is not None:
            found[name] = placed
    return found


def _count(value: object) -> int | None:
    from decimal import Decimal

    if type(value) is int:
        return value
    if isinstance(value, Decimal) and value == int(value):
        return int(value)
    return None


def _safe_write(run: JobRun) -> None:
    try:
        _write(run)
    except STORAGE_ERRORS as exc:
        _log_event("warning", tag="job_run_write_failed", job=run.job, error=error_code(exc))
