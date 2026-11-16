"""Scheduled and manual jobs. Each job records its own run."""

from __future__ import annotations

from typing import Any, Callable

import ingest_jobs
import job_runs
from http_common import _log_event

# Jobs with no kill switch. Later milestones add a switch name here.
SWITCHES: dict[str, str] = {
    "ingest_daily": "ingestEnabled",
    "weekly_refresh": "ingestEnabled",
    "backfill_prices": "ingestEnabled",
    "backfill_fundamentals": "ingestEnabled",
    "screen": "ingestEnabled",
    "backfill_monthly_stats": "ingestEnabled",
    "backtest": "ingestEnabled",
}

Handler = Callable[..., dict[str, Any]]


def _noop(_event: dict[str, Any], _run: job_runs.JobRun, _context: Any = None) -> dict[str, Any]:
    return {"ok": True}


def _may_resume(job: str) -> bool:
    switch = switch_for(job)
    if not switch:
        return True
    import kill_switch

    return kill_switch.is_enabled(switch)


def _tick(_event: dict[str, Any], _run: job_runs.JobRun, _context: Any = None) -> dict[str, Any]:
    import chunked

    chunked.resume_stalled(enabled=_may_resume)
    return {"ok": True}


def _daily(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    return ingest_jobs.ingest_daily(event, context)


def _weekly(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    result = ingest_jobs.weekly_refresh(event, context)
    if result.get("status") == "done":
        result["monthly"] = _append_monthly(event, context)
    return result


def _append_monthly(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Rewrite the open month without failing the weekly refresh that already finished.

    A short remainder is left for the next weekly run. An error is recorded
    on the result and does not change the weekly status.
    """
    remaining = 10**9
    if context is not None and hasattr(context, "get_remaining_time_in_millis"):
        remaining = int(context.get_remaining_time_in_millis())
    if remaining < 120_000:
        return {"ok": False, "status": "deferred"}
    try:
        import monthly_stats

        return monthly_stats.append_latest(event, context)
    except Exception as exc:
        _log_event("error", tag="monthly_stats", error=type(exc).__name__)
        return {"ok": False, "status": "failed"}


def _prices(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    return ingest_jobs.backfill_prices(event, context)


def _fundamentals(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    return ingest_jobs.backfill_fundamentals(event, context)


def _filings(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    return ingest_jobs.resume_filings(event, context)


def _universe_refresh(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    return ingest_jobs.resume_universe(event, context)


def _universe_build(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    return ingest_jobs.resume_build(event, context)


def _adjusted(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    return ingest_jobs.resume_adjusted(event, context)


def _screen(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    import screen

    return screen.run(event, context)


def _monthly(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    import monthly_stats

    return monthly_stats.run(event, context)


def _backtest(event: dict[str, Any], _run: job_runs.JobRun, context: Any = None) -> dict[str, Any]:
    import backtest

    return backtest.run(event, context)


JOBS = {
    "noop": _noop,
    "tick": _tick,
    "ingest_daily": _daily,
    "weekly_refresh": _weekly,
    "backfill_prices": _prices,
    "backfill_fundamentals": _fundamentals,
    ingest_jobs.UNIVERSE_REFRESH_JOB: _universe_refresh,
    ingest_jobs.UNIVERSE_BUILD_JOB: _universe_build,
    ingest_jobs.ADJUSTED_JOB: _adjusted,
    "screen": _screen,
    "backfill_monthly_stats": _monthly,
    "backtest": _backtest,
}


def handler_for(job: str) -> Handler | None:
    """The function for a job, including a per-day filings refresh."""
    found = JOBS.get(job)
    if found is not None:
        return found
    if job.startswith(ingest_jobs.FILINGS_JOB_PREFIX):
        return _filings
    return None


def switch_for(job: str) -> str:
    if job.startswith(ingest_jobs.FILINGS_JOB_PREFIX) or job in {
        ingest_jobs.UNIVERSE_REFRESH_JOB,
        ingest_jobs.UNIVERSE_BUILD_JOB,
        ingest_jobs.ADJUSTED_JOB,
    }:
        return "ingestEnabled"
    return SWITCHES.get(job, "")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    job = str((event or {}).get("job") or "")
    handler = handler_for(job)
    if handler is None:
        _log_event("error", tag="unknown_job", job=job)
        return {"ok": False, "error": "unknown job"}
    switch = switch_for(job)
    with job_runs.record(job) as run:
        if switch:
            import kill_switch

            if not kill_switch.is_enabled(switch):
                run.skip()
                return {"ok": True, "status": "skipped_disabled"}
        result = handler(event, run, context)
        job_runs.apply_result(run, result)
        return result
