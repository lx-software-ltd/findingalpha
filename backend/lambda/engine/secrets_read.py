"""Read a JSON secret at call time. The value is never logged."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

_TTL_SECONDS = 300
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class NotConfigured(Exception):
    """The secret is missing or does not contain the required keys."""

    def __init__(self, secret_id: str) -> None:
        super().__init__(secret_id)
        self.secret_id = secret_id


def clear_cache() -> None:
    _cache.clear()


def read_json_secret(
    secret_id: str,
    required_keys: tuple[str, ...] | list[str],
    *,
    client: Any = None,
    now: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Return the secret JSON. Cache a valid payload for five minutes."""
    current = now()
    cached = _cache.get(secret_id)
    if cached is not None and current - cached[0] < _TTL_SECONDS:
        _require(secret_id, cached[1], required_keys)
        return cached[1]
    payload = _load(secret_id, client)
    _require(secret_id, payload, required_keys)
    _cache[secret_id] = (current, payload)
    return payload


def _load(secret_id: str, client: Any) -> dict[str, Any]:
    if client is None:
        import boto3

        client = boto3.client("secretsmanager")
    try:
        raw = client.get_secret_value(SecretId=secret_id)["SecretString"]
        parsed = json.loads(raw)
    except Exception as exc:
        # The id stays out of the log. CodeQL treats that name as sensitive.
        logger.info("secret read failed error=%s", type(exc).__name__)
        raise NotConfigured(secret_id) from None
    if not isinstance(parsed, dict):
        raise NotConfigured(secret_id)
    return parsed


def _require(secret_id: str, payload: dict[str, Any], required_keys: tuple[str, ...] | list[str]) -> None:
    for key in required_keys:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise NotConfigured(secret_id)
