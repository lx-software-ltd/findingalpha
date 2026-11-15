"""Errors that mean storage could not be reached, and how to name them in logs."""

from __future__ import annotations

from botocore.exceptions import BotoCoreError, ClientError
from config import MissingSetting

STORAGE_ERRORS: tuple[type[BaseException], ...] = (ClientError, BotoCoreError, MissingSetting)


def error_code(exc: BaseException) -> str:
    """AWS error code for a ``ClientError``, otherwise the exception class name."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if code:
            return str(code)
    return type(exc).__name__
