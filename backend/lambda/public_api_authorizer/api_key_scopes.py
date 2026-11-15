"""Public API key tiers, scopes, and CIDR checks.

Mint (``scripts/manage-public-api-keys.py``) and the authorizer share this
module so a key cannot be stored with a scope the authorizer would drop.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from public_api_scopes_generated import ALL_SCOPES, TIERS


def key_tier(item: dict[str, Any]) -> str:
    return str(item.get("tier") or "").strip()


def tier_record(item: dict[str, Any]) -> dict[str, Any] | None:
    record = TIERS.get(key_tier(item))
    if not isinstance(record, dict):
        return None
    return record


def tier_allows(item: dict[str, Any]) -> bool:
    """The row's tier must be one this product has built."""
    record = tier_record(item)
    return bool(record and record.get("enabled"))


def key_allows_write(item: dict[str, Any]) -> bool:
    """True when the tier may write and this key opted in. Missing means read-only."""
    record = tier_record(item)
    if not record or not record.get("mayWrite"):
        return False
    raw = item.get("allowWrite")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return False


def normalize_scopes(item: dict[str, Any]) -> list[str]:
    """Scopes on the row that this tier is allowed to hold. Unknown scopes are dropped."""
    record = tier_record(item)
    if not record or not record.get("enabled"):
        return []
    allowed = set(record.get("scopes") or ())
    raw = item.get("scopes")
    found: set[str] = set()
    if isinstance(raw, list):
        found.update(str(scope).strip() for scope in raw if str(scope).strip() in ALL_SCOPES)
    elif isinstance(raw, str) and raw.strip():
        found.update(part.strip() for part in raw.split(",") if part.strip() in ALL_SCOPES)
    return sorted(scope for scope in found if scope in allowed)


def scopes_csv(scopes: list[str]) -> str:
    return ",".join(scopes)


def parse_cidrs(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for entry in raw:
        text = str(entry or "").strip()
        if not text:
            continue
        try:
            ipaddress.ip_network(text, strict=False)
        except ValueError:
            continue
        out.append(text)
    return out


def ip_allowed(source_ip: str, cidrs: list[str]) -> bool:
    """Fail closed when a CIDR list is set and the client IP is missing or outside it."""
    if not cidrs:
        return True
    text = (source_ip or "").strip()
    if not text:
        return False
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def source_ip_from_event(event: dict[str, Any]) -> str:
    http = (event.get("requestContext") or {}).get("http") or {}
    raw = http.get("sourceIp") or (event.get("requestContext") or {}).get("identity", {}).get("sourceIp")
    return str(raw or "").strip()
