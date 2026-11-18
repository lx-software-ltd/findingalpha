"""Admin HTTP API. Long work does not run here."""

from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
from typing import Any

from http_common import _claims, _json_response, _require_admin, _route, not_found
from owner_tasks import list_tasks, put_task
from research_api import backtest_by_id, latest_screen, list_backtests, screen_by_date
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
    entries = [
        *doc["factors"],
        *[
            doc[key]
            for key in ("composite", "screen", "universe", "fundamentals", "backtest")
            if isinstance(doc.get(key), dict)
        ],
    ]
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
    parsed = _run_params(name, event)
    if isinstance(parsed, str):
        return _json_response(400, {"message": parsed})
    params, chosen = parsed
    if name == "backtest" and chosen is not None:
        import backtest
        import store

        conflict = backtest.size_conflict(store.get("JOB#backtest", "STATE") or {}, chosen)
        if conflict:
            return _json_response(409, {"message": conflict})
    actor = str(event.get("actor") or "") if _key_caller(event) else str(_claims(event).get("sub") or "")
    if params:
        _invoke_engine(name, actor, params)
    else:
        _invoke_engine(name, actor)
    import audit

    target = name if chosen is None else f"{name} {chosen}"
    if params.get("confirmDeletion") is True:
        target = f"{name} confirmDeletion"
    audit.write(actor, "job.run", target, event)
    accepted: dict[str, Any] = {"accepted": True}
    if "portfolioSize" in params:
        accepted["portfolioSize"] = params["portfolioSize"]
    return _json_response(202, accepted)


def _request_object(event: dict[str, Any]) -> dict[str, Any] | None:
    """The JSON object in the body. ``{}`` when the body is absent. None when it is unreadable."""
    raw = event.get("body")
    if event.get("isBase64Encoded") and isinstance(raw, str) and raw:
        try:
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return None
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {}
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _run_params(name: str, event: dict[str, Any]) -> str | tuple[dict[str, int], int | None]:
    """Params to forward and the backtest size, or the refusal message."""
    body = _request_object(event)
    if body is None:
        return "body must be a JSON object"
    if name == "kb_sync_check":
        if not body:
            return {}, None
        if set(body) == {"confirmDeletion"} and body.get("confirmDeletion") is True:
            return {"confirmDeletion": True}, None
        return "only confirmDeletion true is allowed"
    if not body:
        if name != "backtest":
            return {}, None
        import methodology

        return {}, int(methodology.load()["backtest"]["portfolioSize"])
    if name != "backtest":
        return "this job does not take a body"
    if set(body) != {"portfolioSize"}:
        return "only portfolioSize is allowed"
    raw = body["portfolioSize"]
    if isinstance(raw, bool) or not isinstance(raw, int):
        return _size_message()
    import backtest
    import methodology

    register = methodology.load()
    size = backtest.portfolio_size(raw, register)
    if size is None:
        return _size_message(register)
    return {"portfolioSize": size}, size


def _size_message(register: dict[str, Any] | None = None) -> str:
    if register is None:
        import methodology

        register = methodology.load()
    bounds = register["backtest"]
    return f"portfolioSize must be an integer from {bounds['portfolioSizeMin']} to {bounds['portfolioSizeMax']}"


def _invoke_engine(name: str, sub: str, params: dict[str, Any] | None = None) -> None:
    function = os.environ.get("ENGINE_FUNCTION_NAME", "")
    if not function:
        return
    import boto3

    payload: dict[str, Any] = {"job": name, "trigger": "manual", "by": sub}
    if params:
        payload["params"] = params
    boto3.client("lambda").invoke(
        FunctionName=function,
        InvocationType="Event",
        Payload=json.dumps(payload).encode(),
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


def _is_screen_date(method: str, path: str) -> bool:
    parts = path.strip("/").split("/")
    return method == "GET" and len(parts) == 2 and parts[0] == "screens" and parts[1] != "latest"


def _is_backtest_id(method: str, path: str) -> bool:
    parts = path.strip("/").split("/")
    return method == "GET" and len(parts) == 2 and parts[0] == "backtests"


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
    Route("GET", "/screens/latest", latest_screen, "jwt", key_scope="research"),
    Route("GET", "/screens/", screen_by_date, "jwt", match=_is_screen_date, key_scope="research"),
    Route("GET", "/backtests", list_backtests, "jwt", key_scope="research"),
    Route("GET", "/backtests/", backtest_by_id, "jwt", match=_is_backtest_id, key_scope="research"),
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
