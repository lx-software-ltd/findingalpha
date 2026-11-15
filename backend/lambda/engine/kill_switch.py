"""Kill switches fail closed: the stack flag and the runtime setting must both be on."""

from __future__ import annotations

import re
from typing import Any

from config import env_flag
from http_common import _log_event
from storage_errors import STORAGE_ERRORS

SETTINGS_PK = "SETTINGS#global"
SETTINGS_SK = "META"


def _env_name(name: str) -> str:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()
    return snake


def is_enabled(name: str, settings: dict[str, Any] | None = None) -> bool:
    """True only when the environment flag and the settings attribute are both true.

    ``name`` is the camelCase settings attribute, such as ``ingestEnabled``.
    A missing variable, a missing row, or a read error is false.
    """
    enabled = _both_on(name, settings)
    if not enabled:
        _log_event("info", tag="kill_switch", name=name, enabled=False)
    return enabled


def _both_on(name: str, settings: dict[str, Any] | None) -> bool:
    if not env_flag(_env_name(name), default=False):
        return False
    row = settings if settings is not None else _read_settings()
    if row is None:
        return False
    value = row.get(name)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_settings() -> dict[str, Any] | None:
    try:
        import store

        return store.get(SETTINGS_PK, SETTINGS_SK)
    except STORAGE_ERRORS:
        return None
