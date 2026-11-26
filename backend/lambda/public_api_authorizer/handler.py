"""HTTP API Lambda authorizer for the partner API token routes.

Validates a token against hashed key records stored in the records DynamoDB
table (``pk = APIKEY#<scrypt-hex>``, ``sk = META``). The token arrives as
``Authorization: Bearer <token>`` or, for callers that have not moved yet,
as the previous ``x-api-key`` header carrying an ``fapk_`` token. Only the
scrypt digest of a token is ever persisted. Logs carry the first eight hex
characters of that digest (``digest_prefix``) and ``auth_scheme``
(``bearer`` or ``legacy``), never the token and never the full digest. The
plaintext token is shown once at mint time
(``scripts/manage-public-api-keys.py``).

Returns the API Gateway v2 simple authorizer response. API Gateway does
not cache the verdict. A listed identity source that is missing is
rejected before this function runs, so the optional credential headers
are not identity sources. Callers send one of them. This function never
denies based on method. Write methods are enforced by the engine using
the forwarded ``write`` flag. The scheme ``Bearer`` is accepted in any
letter case. A legacy token must start with ``fapk_``. A missing token
is a denial. When both headers are present, a parseable Bearer token
wins.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from api_key_hash import hash_api_key
from api_key_scopes import (
    ip_allowed,
    key_allows_write,
    key_tier,
    normalize_scopes,
    parse_cidrs,
    scopes_csv,
    source_ip_from_event,
    tier_allows,
)
from botocore.exceptions import ClientError

API_KEY_PK_PREFIX = "APIKEY#"
MAX_API_KEY_LEN = 256
LAST_USED_MIN_INTERVAL = timedelta(seconds=60)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ddb = boto3.resource("dynamodb")


def _deny() -> dict[str, Any]:
    return {"isAuthorized": False}


def _log(level: str, **fields: Any) -> None:
    line = json.dumps({key: value for key, value in fields.items() if value is not None}, default=str)
    if level == "warning":
        logger.warning(line)
    else:
        logger.info(line)


def _header_value(event: dict[str, Any], name: str) -> str | None:
    # HTTP API payload 2.0 lower-cases header names. Tests may send either case.
    headers = event.get("headers") or {}
    if not isinstance(headers, dict):
        return None
    for header_name, value in headers.items():
        if str(header_name).lower() == name and isinstance(value, str):
            return value
    return None


def _bearer_token(raw: str | None) -> str | None:
    if raw is None:
        return None
    scheme, separator, token = raw.strip().partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    key = token.strip()
    if not key or len(key) > MAX_API_KEY_LEN or " " in key:
        return None
    return key


def _legacy_token(raw: str | None) -> str | None:
    if raw is None:
        return None
    key = raw.strip()
    if not key.startswith("fapk_") or len(key) > MAX_API_KEY_LEN:
        return None
    return key


def _extract_api_key(event: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return the token and ``bearer`` or ``legacy``. Bearer wins when both parse."""
    bearer = _bearer_token(_header_value(event, "authorization"))
    if bearer is not None:
        return bearer, "bearer"
    legacy = _legacy_token(_header_value(event, "x-api-key"))
    if legacy is not None:
        return legacy, "legacy"
    return None, None


def _is_expired(expires_at: Any, now: datetime) -> bool:
    """True when ``expiresAt`` is an ISO date or datetime in the past.

    An unparseable value fails closed so a corrupted row cannot grant access.
    """
    if expires_at in (None, ""):
        return False
    try:
        parsed = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= now


def _should_touch_last_used(item: dict[str, Any], now: datetime) -> bool:
    raw = item.get("lastUsedAt")
    if not raw:
        return True
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return now - parsed >= LAST_USED_MIN_INTERVAL


def _touch_last_used(table: Any, item: dict[str, Any], source_ip: str, now: datetime) -> None:
    if not _should_touch_last_used(item, now):
        return
    try:
        table.update_item(
            Key={"pk": item["pk"], "sk": item.get("sk") or "META"},
            UpdateExpression="SET lastUsedAt = :t, lastSourceIp = :ip",
            ExpressionAttributeValues={":t": now.isoformat(), ":ip": source_ip or "unknown"},
        )
    except Exception as exc:
        _log(
            "warning",
            tag="public_api_key_last_used_failed",
            error=type(exc).__name__,
            key_id=item.get("keyId"),
        )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    key, auth_scheme = _extract_api_key(event)
    request_id = (event.get("requestContext") or {}).get("requestId")
    source_ip = source_ip_from_event(event)

    def _event_log(level: str, **fields: Any) -> None:
        _log(level, auth_scheme=auth_scheme, **fields)

    if key is None:
        _event_log(
            "info", tag="public_api_key_denied", reason="missing_key", request_id=request_id, source_ip=source_ip
        )
        return _deny()

    digest = hash_api_key(key)
    digest_prefix = digest[:8]
    table = _ddb.Table(os.environ["RECORDS_TABLE_NAME"])
    try:
        res = table.get_item(Key={"pk": f"{API_KEY_PK_PREFIX}{digest}", "sk": "META"})
    except ClientError as exc:
        _event_log(
            "warning",
            tag="public_api_key_denied",
            reason="ddb_error",
            error_code=exc.response.get("Error", {}).get("Code"),
            digest_prefix=digest_prefix,
            request_id=request_id,
            source_ip=source_ip,
        )
        return _deny()

    item = res.get("Item")
    if not item:
        _event_log(
            "info",
            tag="public_api_key_denied",
            reason="unknown_key",
            digest_prefix=digest_prefix,
            request_id=request_id,
            source_ip=source_ip,
        )
        return _deny()

    key_id = item.get("keyId")
    now = datetime.now(timezone.utc)
    if item.get("revoked"):
        _event_log(
            "info",
            tag="public_api_key_denied",
            reason="revoked",
            key_id=key_id,
            request_id=request_id,
            source_ip=source_ip,
        )
        return _deny()
    if _is_expired(item.get("expiresAt"), now):
        _event_log(
            "info",
            tag="public_api_key_denied",
            reason="expired",
            key_id=key_id,
            request_id=request_id,
            source_ip=source_ip,
        )
        return _deny()
    if not tier_allows(item):
        _event_log(
            "info",
            tag="public_api_key_denied",
            reason="tier",
            key_id=key_id,
            request_id=request_id,
            source_ip=source_ip,
        )
        return _deny()

    scopes = normalize_scopes(item)
    if not scopes:
        _event_log(
            "info",
            tag="public_api_key_denied",
            reason="bad_scope",
            key_id=key_id,
            request_id=request_id,
            source_ip=source_ip,
        )
        return _deny()

    cidrs = parse_cidrs(item.get("allowedCidrs"))
    if not ip_allowed(source_ip, cidrs):
        _event_log(
            "info",
            tag="public_api_key_denied",
            reason="cidr",
            key_id=key_id,
            request_id=request_id,
            source_ip=source_ip,
        )
        return _deny()

    _touch_last_used(table, item, source_ip, now)
    write_flag = "1" if key_allows_write(item) else "0"
    _event_log(
        "info",
        tag="public_api_key_allowed",
        key_id=key_id,
        request_id=request_id,
        source_ip=source_ip,
        write=write_flag,
    )
    return {
        "isAuthorized": True,
        "context": {
            "keyId": str(key_id or ""),
            "label": str(item.get("label") or ""),
            "tier": key_tier(item),
            "scopes": scopes_csv(scopes),
            "write": write_flag,
        },
    }
