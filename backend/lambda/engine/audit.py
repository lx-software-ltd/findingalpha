"""One audit row per state-changing API call."""

from __future__ import annotations

import time
from typing import Any

import runtime
from config import audit_table_name
from http_common import _log_event, _request_id
from storage_errors import STORAGE_ERRORS, error_code


def write(actor: str | None, action: str, target: str, event: dict[str, Any]) -> None:
    """``actor`` is a Cognito ``sub`` or ``apikey:<keyId>``."""
    if not actor:
        return
    try:
        table = runtime.ddb().Table(audit_table_name())
        stamp = int(time.time() * 1000)
        table.put_item(
            Item={
                "pk": f"USER#{actor}",
                "sk": f"{stamp}#{action}",
                "target": target,
                "requestId": _request_id(event),
            }
        )
    except STORAGE_ERRORS as exc:
        _log_event("warning", tag="audit_write_failed", action=action, error=error_code(exc))
