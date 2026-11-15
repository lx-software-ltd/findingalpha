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


def _safe_write(run: JobRun) -> None:
    try:
        _write(run)
    except STORAGE_ERRORS as exc:
        _log_event("warning", tag="job_run_write_failed", job=run.job, error=error_code(exc))
