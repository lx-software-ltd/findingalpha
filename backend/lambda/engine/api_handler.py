"""Admin HTTP API. Long work does not run here."""

from __future__ import annotations

from typing import Any

from http_common import _claims, _json_response, _require_admin, _route, not_found
from router import Route, route_matches


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
