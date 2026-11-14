"""Admin HTTP API. Long work does not run here."""

from __future__ import annotations

from typing import Any

from http_common import _claims, _json_response, _require_admin, _route, not_found
from owner_tasks import list_tasks, put_task
from router import Route, route_matches
from settings import get_settings, put_settings
from system_status import list_runs, status


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


ROUTES = (
    Route("GET", "/health", _health, "none"),
    Route("GET", "/me", _me, "jwt"),
    Route("GET", "/owner-tasks", list_tasks, "jwt"),
    Route("PUT", "/owner-tasks/", put_task, "jwt", kind="prefix"),
    Route("GET", "/settings", get_settings, "jwt"),
    Route("PUT", "/settings", put_settings, "jwt"),
    Route("GET", "/jobs/runs", list_runs, "jwt"),
    Route("GET", "/system/status", status, "jwt"),
)


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    method, path = _route(event)
    for route in ROUTES:
        if not route_matches(route, method, path):
            continue
        if route.auth == "jwt" and _require_admin(event) is None:
            return _json_response(403, {"message": "Forbidden"})
        return route.handler(event)
    return not_found()
