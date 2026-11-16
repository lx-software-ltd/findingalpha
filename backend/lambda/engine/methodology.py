"""The methodology register. Factors read their thresholds from here."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_PATH = Path(__file__).resolve().parent / "contracts" / "methodology.json"
_KEYS = {"version", "universe", "factors", "composite", "screen"}
_FACTOR_KEYS = {"id", "group", "direction", "formula", "implementation", "status"}
_STATUSES = {"provisional", "cited"}
_DIRECTIONS = {"higher", "lower"}
_CITATION_KEYS = ("document", "locator", "quote")


class MethodologyError(ValueError):
    """The register is missing a required field or breaks a rule."""


def load() -> dict[str, Any]:
    """The bundled register."""
    loaded = json.loads(_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise MethodologyError("register must be an object")
    return loaded


def validate(doc: dict[str, Any]) -> None:
    """Raise ``MethodologyError`` when the register breaks a rule."""
    unknown = set(doc) - _KEYS
    if unknown:
        raise MethodologyError(f"unknown key {sorted(unknown)[0]}")
    for key in _KEYS:
        if key not in doc:
            raise MethodologyError(f"missing {key}")
    _status(doc["universe"], "universe")
    factors = doc["factors"]
    if not isinstance(factors, list):
        raise MethodologyError("factors must be a list")
    seen: set[str] = set()
    for factor in factors:
        if not isinstance(factor, dict):
            raise MethodologyError("factor must be an object")
        missing = _FACTOR_KEYS - set(factor)
        if missing:
            raise MethodologyError(f"factor missing {sorted(missing)[0]}")
        name = str(factor["id"])
        if name in seen:
            raise MethodologyError(f"duplicate id {name}")
        seen.add(name)
        if factor["direction"] not in _DIRECTIONS:
            raise MethodologyError(f"{name} direction")
        _status(factor, name)
    _status(doc["composite"], "composite")
    _status(doc["screen"], "screen")
    weights = doc["composite"].get("groupWeights")
    if not isinstance(weights, dict) or not weights:
        raise MethodologyError("group weights")
    total = sum(float(value) for value in weights.values())
    if abs(total - 1.0) > 1e-9:
        raise MethodologyError("group weights must sum to 1")
    percentiles = doc["composite"].get("winsorisePercentiles")
    if not isinstance(percentiles, list) or len(percentiles) != 2:
        raise MethodologyError("percentiles")
    for value in percentiles:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 100:
            raise MethodologyError("percentile outside 0 to 100")


def register_hash(doc: dict[str, Any]) -> str:
    """First 16 hex characters of the canonical register."""
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def factor(factor_id: str) -> dict[str, Any]:
    """One factor from the bundled register."""
    found = next((item for item in load()["factors"] if item.get("id") == factor_id), None)
    if found is None:
        raise MethodologyError(f"unknown factor {factor_id}")
    return found


def parameter(factor_id: str, name: str) -> Any:
    """One parameter of a factor."""
    values = factor(factor_id).get("parameters") or {}
    if name not in values:
        raise MethodologyError(f"{factor_id} missing {name}")
    return values[name]


def composite() -> dict[str, Any]:
    """The composite block."""
    return load()["composite"]


def screen() -> dict[str, Any]:
    """The screen block."""
    return load()["screen"]


def universe() -> dict[str, Any]:
    """The universe block."""
    return load()["universe"]


def _status(item: dict[str, Any], label: str) -> None:
    status = item.get("status") if isinstance(item, dict) else None
    if status not in _STATUSES:
        raise MethodologyError(f"{label} status")
    if status != "cited":
        return
    citation = item.get("citation")
    if not isinstance(citation, dict):
        raise MethodologyError(f"{label} cited without a citation")
    for key in _CITATION_KEYS:
        value = citation.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MethodologyError(f"{label} cited without a citation")
    if len(citation["quote"]) > 200:
        raise MethodologyError(f"{label} citation quote")
