"""Mirror of the dashboard routes for an API key.

A request on ``/v1/partner`` never calls ``_require_admin``. The authorizer
already accepted the key. This module decides which mirrored route that
key may call, and which denial the caller sees.
"""

from __future__ import annotations

from typing import Any

from http_common import _json_response, _parse_json_body, _route, error_body, not_found
from router import Route, route_matches

_WRITE_METHODS = {"PUT", "POST", "DELETE"}
_PUBLIC = "/v1/partner"
# Key rows are listed through this index. A table scan would read every record.
API_KEYS_GSI_PK = "APIKEYS"


def key_context(event: dict[str, Any]) -> dict[str, Any]:
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    context = authorizer.get("lambda") or {}
    if not isinstance(context, dict):
        return {}
    return context


def scopes_from_key_context(key_ctx: dict[str, Any]) -> set[str]:
    raw = key_ctx.get("scopes") or ""
    if isinstance(raw, list):
        return {str(scope).strip() for scope in raw if str(scope).strip()}
    return {part.strip() for part in str(raw).split(",") if part.strip()}


def key_context_allows_write(key_ctx: dict[str, Any]) -> bool:
    """API Gateway context values are strings. ``"1"`` is the allow flag."""
    return str(key_ctx.get("write") or "") == "1"


def writes_enabled() -> bool:
    from config import env_flag

    return env_flag("PUBLIC_API_WRITES_ENABLED", False)


def settings_body_allowed(body: dict[str, Any]) -> bool:
    """A key may only turn switches off. Any other value is owner-only."""
    if not isinstance(body, dict) or not body:
        return False
    return all(value is False for value in body.values())


def _routes() -> tuple[Route, ...]:
    from api_handler import ROUTES

    return ROUTES


def resolve(method: str, path: str) -> Route | None:
    """Strip ``/v1/partner`` and return the dashboard route, or None."""
    if path == _PUBLIC:
        return None
    if not path.startswith(f"{_PUBLIC}/"):
        return None
    inner = path[len(_PUBLIC) :]
    for route in _routes():
        if route_matches(route, method, inner):
            return route
    return None


def deny_reason(
    method: str,
    route: Route | None,
    key_ctx: dict[str, Any],
    body: dict[str, Any],
) -> str | None:
    """``None`` means the key may call the route.

    A PUT, POST or DELETE that is not marked ``key_write`` is owner-only.
    The method is what makes it a write. ``key_write`` only means a key
    may make that write.
    """
    if route is None or route.key_scope is None:
        return "not_mirrored"
    scopes = scopes_from_key_context(key_ctx)
    if route.key_scope not in scopes:
        return "scope"
    if method not in _WRITE_METHODS and not route.key_write:
        return None
    if not route.key_write:
        return "owner_only"
    if not writes_enabled():
        return "writes_disabled"
    if not key_context_allows_write(key_ctx):
        return "key_read_only"
    if route.pattern == "/settings" and not settings_body_allowed(body):
        return "owner_only"
    return None


def _probe_body(route: Route) -> dict[str, Any]:
    if route.pattern == "/settings" and route.key_write:
        return {"ingestEnabled": False}
    return {}


def route_index(key_ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Mirrored routes this key may call. Owner-only routes are absent."""
    rows: list[dict[str, Any]] = []
    for route in _routes():
        if route.key_scope is None:
            continue
        if deny_reason(route.method, route, key_ctx, _probe_body(route)):
            continue
        rows.append(
            {
                "method": route.method,
                "path": f"{_PUBLIC}{route.pattern}",
                "scope": route.key_scope,
                "write": route.key_write,
            }
        )
    return rows


def _forward(event: dict[str, Any], method: str, inner: str, key_ctx: dict[str, Any]) -> dict[str, Any]:
    forward = dict(event)
    forward["actor"] = f"apikey:{key_ctx.get('keyId') or ''}"
    request = dict(event.get("requestContext") or {})
    http = dict(request.get("http") or {})
    http["method"] = method
    http["path"] = inner
    request["http"] = http
    forward["requestContext"] = request
    return forward


def list_keys() -> dict[str, Any]:
    """Dashboard list. The digest and the table key never leave the function."""
    import store

    rows: list[dict[str, Any]] = []
    fields = (
        "keyId",
        "label",
        "tier",
        "scopes",
        "allowWrite",
        "revoked",
        "createdAt",
        "expiresAt",
        "lastUsedAt",
        "allowedCidrs",
    )
    for item in store.query_gsi1(API_KEYS_GSI_PK):
        if item.get("sk") not in (None, "META"):
            continue
        rows.append({field: item.get(field) for field in fields if field in item})
    rows.sort(key=lambda row: str(row.get("createdAt") or ""))
    return _json_response(200, {"keys": rows, "writesEnabled": writes_enabled()})


def handle(event: dict[str, Any]) -> dict[str, Any]:
    method, path = _route(event)
    if path != _PUBLIC and not path.startswith(f"{_PUBLIC}/"):
        return not_found()
    key_ctx = key_context(event)
    if not str(key_ctx.get("keyId") or "").strip():
        return _json_response(401, error_body(401, "Unauthorized"))
    if method == "GET" and path == _PUBLIC:
        return _json_response(200, {"routes": route_index(key_ctx)})
    route = resolve(method, path)
    body = _parse_json_body(event) if method in _WRITE_METHODS else {}
    reason = deny_reason(method, route, key_ctx, body)
    if reason is not None or route is None:
        if method in _WRITE_METHODS:
            return _json_response(403, error_body(403, "Forbidden", reason=reason or "not_mirrored"))
        return not_found()
    inner = path[len(_PUBLIC) :]
    return route.handler(_forward(event, method, inner, key_ctx))
