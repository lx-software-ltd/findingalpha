"""Scheduled and manual jobs. Each job records its own run."""

from __future__ import annotations

from typing import Any

import job_runs
from http_common import _log_event

# Jobs with no kill switch. Later milestones add a switch name here.
SWITCHES: dict[str, str] = {}


def _noop(_event: dict[str, Any], _run: job_runs.JobRun) -> dict[str, Any]:
    return {"ok": True}


def _tick(_event: dict[str, Any], _run: job_runs.JobRun) -> dict[str, Any]:
    return {"ok": True}


JOBS = {
    "noop": _noop,
    "tick": _tick,
}


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    job = str((event or {}).get("job") or "")
    handler = JOBS.get(job)
    if handler is None:
        _log_event("error", tag="unknown_job", job=job)
        return {"ok": False, "error": "unknown job"}
    switch = SWITCHES.get(job)
    with job_runs.record(job) as run:
        if switch:
            import kill_switch

            if not kill_switch.is_enabled(switch):
                run.skip()
                return {"ok": True, "status": "skipped_disabled"}
        return handler(event, run)
