"""The methodology register. Factors read their thresholds from here."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import inspect
import json
from pathlib import Path
from typing import Any

_PATH = Path(__file__).resolve().parent / "contracts" / "methodology.json"
_FUNDAMENTALS = _PATH.parent / "fundamentals.json"
_KEYS = {"version", "universe", "factors", "composite", "screen", "fundamentals"}
_FACTOR_KEYS = {"id", "group", "direction", "formula", "implementation", "status"}
_STATUSES = {"provisional", "cited"}
_DIRECTIONS = {"higher", "lower"}
_CITATION_KEYS = ("document", "locator", "quote")
_FACTOR_MODULES = ("factors_quality", "factors_value", "factors_trend")
_FILTER_OPS = {">", ">=", "<", "<=", "=="}
_CACHE: tuple[int, dict[str, Any]] | None = None


class MethodologyError(ValueError):
    """The register is missing a required field or breaks a rule."""


def load() -> dict[str, Any]:
    """The bundled register. The file is read again only when it changes."""
    global _CACHE
    stamp = _PATH.stat().st_mtime_ns
    if _CACHE is None or _CACHE[0] != stamp:
        loaded = json.loads(_PATH.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise MethodologyError("register must be an object")
        _CACHE = (stamp, loaded)
    return copy.deepcopy(_CACHE[1])


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
    _status(doc["fundamentals"], "fundamentals")
    if doc["fundamentals"].get("unreportedDebt") not in {"zero", "missing"}:
        raise MethodologyError("unreportedDebt")
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
    if float(percentiles[0]) >= float(percentiles[1]):
        raise MethodologyError("percentiles")
    _share(doc["composite"].get("minFactorsPerGroupShare"))
    _whole(doc["composite"].get("minSectorSize"), "minSectorSize")
    groups = {str(factor["group"]) for factor in factors}
    for name in weights:
        if str(name) not in groups:
            raise MethodologyError(f"group weight {name} has no factor")
    _screen(doc["screen"], {str(factor["id"]) for factor in factors})
    _implementations(factors)


def _share(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
        raise MethodologyError("minFactorsPerGroupShare")


def _whole(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MethodologyError(label)


def _number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _screen(screen: dict[str, Any], factor_ids: set[str]) -> None:
    _whole(screen.get("shortlistSize"), "shortlistSize")
    filters = screen.get("hardFilters")
    if not isinstance(filters, list) or not filters:
        raise MethodologyError("hard filters")
    known = _snapshot_fields() | factor_ids
    for rule in filters:
        if not isinstance(rule, dict):
            raise MethodologyError("hard filter")
        field = str(rule.get("field") or "")
        if field not in known:
            raise MethodologyError(f"unknown screen field {field}")
        if rule.get("op") not in _FILTER_OPS or not _number(rule.get("value")):
            raise MethodologyError(f"hard filter {field}")


def _snapshot_fields() -> set[str]:
    raw = json.loads(_FUNDAMENTALS.read_text(encoding="utf-8"))
    names: set[str] = {"marketCap", "enterpriseValue"}
    for field in raw.get("flows") or {}:
        names.add(f"{field}_ttm")
    for field in raw.get("stocks") or {}:
        names.add(str(field))
        names.add(f"{field}_avg")
    return names


def _implementations(factors: list[dict[str, Any]]) -> None:
    named: set[str] = set()
    for factor in factors:
        path = str(factor["implementation"])
        named.add(path)
        function = _callable(path)
        params = factor.get("parameters") or {}
        if not isinstance(params, dict):
            raise MethodologyError(f"{factor['id']} parameters")
        for name in _parameters_read(function):
            if not _number(params.get(name)):
                raise MethodologyError(f"{factor['id']} missing {name}")
    for module_name in _FACTOR_MODULES:
        module = importlib.import_module(module_name)
        for name, value in vars(module).items():
            if name.startswith("_") or not callable(value) or getattr(value, "__module__", None) != module_name:
                continue
            if f"{module_name}.{name}" not in named:
                raise MethodologyError(f"unregistered {module_name}.{name}")


def _parameters_read(function: Any) -> list[str]:
    """Parameter names the function reads from ``params``. The source is the check."""
    tree = ast.parse(inspect.getsource(function))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name):
            continue
        if node.value.id != "params" or not isinstance(node.slice, ast.Constant):
            continue
        if isinstance(node.slice.value, str) and node.slice.value not in found:
            found.append(node.slice.value)
    return found


def _callable(path: str) -> Any:
    module_name, separator, func_name = path.partition(".")
    if not separator or not module_name.isidentifier() or not func_name.isidentifier():
        raise MethodologyError(f"unknown implementation {path}")
    try:
        function = getattr(importlib.import_module(module_name), func_name)
    except (ImportError, AttributeError) as exc:
        raise MethodologyError(f"unknown implementation {path}") from exc
    if not callable(function):
        raise MethodologyError(f"unknown implementation {path}")
    return function


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
