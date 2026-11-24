"""HTTP helpers shared by the admin API."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from runtime import ADMIN_GROUP, logger


def _json_response(status_code: int, payload: dict[str, Any] | list[Any] | str) -> dict[str, Any]:
    body = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": body,
    }


def not_found() -> dict[str, Any]:
    return _json_response(404, {"message": "Not found"})


def _parse_json_body(event: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _claims(event: dict[str, Any]) -> dict[str, Any]:
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )


def _groups_include_admin(claims: dict[str, Any]) -> bool:
    raw = claims.get("cognito:groups")
    if raw is None:
        return False
    if isinstance(raw, list):
        return ADMIN_GROUP in raw
    # API Gateway flattens array claims to "[admin]" or "[viewer, admin]".
    text = str(raw).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    parts = [part.strip() for part in text.split(",") if part.strip()]
    return ADMIN_GROUP in parts


def _require_admin(event: dict[str, Any]) -> dict[str, Any] | None:
    claims = _claims(event)
    if not _groups_include_admin(claims):
        return None
    return claims


def _route(event: dict[str, Any]) -> tuple[str, str]:
    http = event.get("requestContext", {}).get("http", {})
    return http.get("method", ""), http.get("path", "")


def _request_id(event: dict[str, Any]) -> str:
    context = event.get("requestContext", {})
    return context.get("requestId") or context.get("http", {}).get("requestId") or "unknown"


def _log_event(level: str, **fields: Any) -> None:
    payload = {key: value for key, value in fields.items() if value is not None}
    line = json.dumps(payload, default=str)
    if level == "warning":
        logger.warning(line)
    elif level == "error":
        logger.error(line)
    else:
        logger.info(line)


def _decode_cursor(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        pad = "=" * ((4 - len(raw) % 4) % 4)
        blob = base64.urlsafe_b64decode(raw + pad)
        return json.loads(blob.decode("utf-8"))
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _encode_cursor(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
