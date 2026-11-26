"""Owner checklist ticks. The task text lives in the roadmap, not here."""

from __future__ import annotations

import re
from typing import Any

import audit
import timeutil
from http_common import _json_response, _parse_json_body, _require_admin, _route, error_body

_TASK_ID = re.compile(r"^O[0-9]{2}$")
_PK_PREFIX = "OWNER_TASK#"


def _task_id(event: dict[str, Any]) -> str:
    _method, path = _route(event)
    return path.rstrip("/").rsplit("/", 1)[-1]


def list_tasks(_event: dict[str, Any]) -> dict[str, Any]:
    import store

    done = {
        str(item["pk"]).removeprefix(_PK_PREFIX): {"at": str(item.get("at", ""))}
        for item in store.scan_pk_prefix(_PK_PREFIX)
        if str(item.get("pk", "")).startswith(_PK_PREFIX)
    }
    return _json_response(200, {"done": done})


def put_task(event: dict[str, Any]) -> dict[str, Any]:
    claims = _require_admin(event)
    if claims is None:
        return _json_response(403, error_body(403, "Forbidden"))
    task_id = _task_id(event)
    if not _TASK_ID.fullmatch(task_id):
        return _json_response(400, error_body(400, "Unknown task"))
    body = _parse_json_body(event)
    if not isinstance(body.get("done"), bool):
        return _json_response(400, error_body(400, "done must be a boolean"))
    import store

    pk = f"{_PK_PREFIX}{task_id}"
    if body["done"]:
        store.put({"pk": pk, "sk": "META", "at": timeutil.now_iso()})
    else:
        store.delete(pk, "META")
    audit.write(str(claims.get("sub") or ""), "owner_task_set", task_id, event)
    return list_tasks(event)
