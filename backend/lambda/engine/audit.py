"""One audit row per state-changing API call."""

from __future__ import annotations

import time
from typing import Any

import runtime
from botocore.exceptions import ClientError
from config import audit_table_name
from http_common import _log_event, _request_id


def write(actor: str | None, action: str, target: str, event: dict[str, Any]) -> None:
    """``actor`` is a Cognito ``sub`` or ``apikey:<keyId>``."""
    if not actor:
        return
    try:
        table = runtime._ddb.Table(audit_table_name())
        stamp = int(time.time() * 1000)
        table.put_item(
            Item={
                "pk": f"USER#{actor}",
                "sk": f"{stamp}#{action}",
                "target": target,
                "requestId": _request_id(event),
            }
        )
    except ClientError as exc:
        _log_event(
            "warning",
            tag="audit_write_failed",
            action=action,
            error=exc.response.get("Error", {}).get("Code", "ClientError"),
        )
