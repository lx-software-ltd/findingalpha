"""Admin HTTP API. Long work does not run here."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from http_common import _claims, _json_response, _require_admin, _route, not_found
from owner_tasks import list_tasks, put_task
from router import Route, route_matches
from settings import get_settings, put_settings
from system_status import list_runs, status

_JOBS = Path(__file__).resolve().parent / "contracts" / "jobs.json"


def _health(_event: dict[str, Any]) -> dict[str, Any]:
    return _json_response(200, {"ok": True})


def _me(event: dict[str, Any]) -> dict[str, Any]:
    claims = _claims(event)
    return _json_response(
        200,
        {
            "sub": claims.get("sub", ""),
            "email": claims.get("email", ""),
            "groups": claims.get("cognito:groups", ""),
        },
    )


def get_methodology(_event: dict[str, Any]) -> dict[str, Any]:
    """The register, its hash, and how many entries are still provisional."""
    import methodology

    doc = methodology.load()
    entries = [*doc["factors"], doc["composite"], doc["screen"], doc["universe"]]
    return _json_response(
        200,
        {
            "register": doc,
            "hash": methodology.register_hash(doc),
            "counts": {
                "entries": len(entries),
                "provisional": sum(item.get("status") == "provisional" for item in entries),
                "cited": sum(item.get("status") == "cited" for item in entries),
            },
        },
    )


def list_api_keys(_event: dict[str, Any]) -> dict[str, Any]:
    from public_api import list_keys

    return list_keys()


def _job_rows() -> list[dict[str, Any]]:
    raw = json.loads(_JOBS.read_text(encoding="utf-8"))
    jobs = raw.get("jobs") or []
    return [row for row in jobs if isinstance(row, dict) and row.get("name")]


def _key_caller(event: dict[str, Any]) -> bool:
    return str(event.get("actor") or "").startswith("apikey:")


def _engine_runs(name: str) -> bool:
    import jobs_handler

    return jobs_handler.handler_for(name) is not None


def _job_name(event: dict[str, Any]) -> str:
    params = event.get("pathParameters") or {}
    named = params.get("jobName")
    if named:
        return str(named)
    path = str(((event.get("requestContext") or {}).get("http") or {}).get("path") or "")
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "run":
        return parts[1]
    return ""


def run_job(event: dict[str, Any]) -> dict[str, Any]:
    """Start a job the contract allows. The engine runs it after this returns."""
    name = _job_name(event)
    row = next((item for item in _job_rows() if str(item.get("name")) == name), None)
    if row is None:
        return not_found()
    if _key_caller(event):
        allowed = row.get("keyRun") is True
    else:
        allowed = row.get("manualRun") is True and _engine_runs(name)
    if not allowed:
        return not_found()
    if _key_caller(event) and _backfill_finished(name):
        return _json_response(409, {"message": f"{name} already finished"})
    actor = str(event.get("actor") or "") if _key_caller(event) else str(_claims(event).get("sub") or "")
    _invoke_engine(name, actor)
    import audit

    audit.write(actor, "job.run", name, event)
    return _json_response(202, {"accepted": True})


def _invoke_engine(name: str, sub: str) -> None:
    function = os.environ.get("ENGINE_FUNCTION_NAME", "")
    if not function:
        return
    import boto3

    boto3.client("lambda").invoke(
        FunctionName=function,
        InvocationType="Event",
        Payload=json.dumps({"job": name, "trigger": "manual", "by": sub}).encode(),
    )


def latest_universe(_event: dict[str, Any]) -> dict[str, Any]:
    """The newest finished universe: date, size, and the count after each rule."""
    import store

    rows = [row for row in store.query_gsi1("UNIVERSE") if isinstance(row.get("counts"), dict)]
    latest = max(rows, key=lambda row: str(row.get("gsi1sk") or "")) if rows else {}
    return _json_response(200, _universe_payload(latest))


def _universe_payload(latest: dict[str, Any]) -> dict[str, Any]:
    return {
        "asOf": latest.get("asOf") or latest.get("gsi1sk"),
        "members": latest.get("members") or 0,
        "counts": latest.get("counts") or {},
        "sectors": latest.get("sectors") or {},
        "shareSources": latest.get("shareSources") or {},
        "coverage": latest.get("coverage") or {},
        "lastPriceDate": latest.get("lastPriceDate"),
        "backfill": {
            "prices": _progress("backfill_prices"),
            "fundamentals": _progress("backfill_fundamentals"),
        },
    }


def _backfill_finished(job: str) -> bool:
    """A finished backfill starts again from the first month. A key must not do that."""
    if job not in {"backfill_prices", "backfill_fundamentals"}:
        return False
    import store

    item = store.get(f"JOB#{job}", "STATE") or {}
    return item.get("status") == "done"


def _progress(job: str) -> dict[str, Any] | None:
    import store
    from job_runs import position

    return position(store.get(f"JOB#{job}", "STATE") or {})


def _is_job_run(method: str, path: str) -> bool:
    parts = path.strip("/").split("/")
    return method == "POST" and len(parts) == 3 and parts[0] == "jobs" and parts[2] == "run"


ROUTES = (
    Route("GET", "/health", _health, "none"),
    Route("GET", "/me", _me, "jwt"),
    Route("GET", "/owner-tasks", list_tasks, "jwt", key_scope="system"),
    Route("PUT", "/owner-tasks/", put_task, "jwt", kind="prefix"),
    Route("GET", "/settings", get_settings, "jwt", key_scope="system"),
    Route("PUT", "/settings", put_settings, "jwt", key_scope="operate", key_write=True),
    Route("GET", "/jobs/runs", list_runs, "jwt", key_scope="system"),
    Route("POST", "/jobs/", run_job, "jwt", match=_is_job_run, key_scope="operate", key_write=True),
    Route("GET", "/universe/latest", latest_universe, "jwt", key_scope="research"),
    Route("GET", "/system/status", status, "jwt", key_scope="system"),
    Route("GET", "/api-keys", list_api_keys, "jwt"),
    Route("GET", "/methodology", get_methodology, "jwt", key_scope="research"),
)


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    method, path = _route(event)
    if path == "/public" or path.startswith("/public/"):
        from public_api import handle

        return handle(event)
    for route in ROUTES:
        if not route_matches(route, method, path):
            continue
        if route.auth == "jwt" and _require_admin(event) is None:
            return _json_response(403, {"message": "Forbidden"})
        return route.handler(event)
    return not_found()
