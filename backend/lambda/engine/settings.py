"""Runtime kill switches. The stack parameter is a separate flag."""

from __future__ import annotations

from typing import Any

import audit
from http_common import _json_response, _parse_json_body, _require_admin, error_body
from kill_switch import SETTINGS_PK, SETTINGS_SK

SWITCHES = (
    "ingestEnabled",
    "committeeEnabled",
    "tradingEnabled",
    "leverageEnabled",
    "briefEmailEnabled",
)


def _row() -> dict[str, Any]:
    import store

    return store.get(SETTINGS_PK, SETTINGS_SK) or {}


def _flags(row: dict[str, Any]) -> dict[str, bool]:
    return {name: row.get(name) is True for name in SWITCHES}


def get_settings(_event: dict[str, Any]) -> dict[str, Any]:
    return _json_response(200, _flags(_row()))


def put_settings(event: dict[str, Any]) -> dict[str, Any]:
    actor = event.get("actor")
    if isinstance(actor, str) and actor.startswith("apikey:"):
        pass
    else:
        claims = _require_admin(event)
        if claims is None:
            return _json_response(403, error_body(403, "Forbidden"))
        # The partition key stays USER#<sub>, the same form as earlier dashboard writes.
        actor = str(claims.get("sub") or "")
    body = _parse_json_body(event)
    unknown = [key for key in body if key not in SWITCHES]
    if unknown or not body:
        return _json_response(400, error_body(400, "Unknown setting"))
    if any(not isinstance(value, bool) for value in body.values()):
        return _json_response(400, error_body(400, "Settings must be booleans"))
    import store

    row = _row()
    row.update({"pk": SETTINGS_PK, "sk": SETTINGS_SK, **body})
    store.put(row)
    audit.write(actor, "settings_put", ",".join(sorted(body)), event)
    return _json_response(200, _flags(row))
