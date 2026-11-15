"""Process environment accessors.

Read ``os.environ`` on each call. Tests patch the environment after import, so
these helpers must not cache values at module load.
"""

from __future__ import annotations

import os

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSEY = frozenset({"0", "false", "no", "off"})


class MissingSetting(KeyError):
    """A required environment variable is unset."""


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingSetting(name)
    return value


def records_table_name() -> str:
    return _required("RECORDS_TABLE_NAME")


def audit_table_name() -> str:
    return _required("AUDIT_LOG_TABLE_NAME")


def data_bucket_name() -> str:
    return _required("DATA_BUCKET_NAME")


def flag_value(raw: object, default: bool = False) -> bool:
    """Parse one boolean token. A blank or unknown token returns ``default``."""
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if not text:
        return default
    if text in _TRUTHY:
        return True
    if text in _FALSEY:
        return False
    return default


def env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable. Missing means ``default``."""
    if name not in os.environ:
        return default
    return flag_value(os.environ.get(name), default)
