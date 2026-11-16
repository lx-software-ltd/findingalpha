"""Apply the register's hard filters and keep the shortlist."""

from __future__ import annotations

from typing import Any

_OPS = {
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    "==": lambda left, right: left == right,
}


def failed_filters(row: dict[str, Any], register: dict[str, Any]) -> list[str]:
    """The ids of the hard filters the row misses. A missing composite is its own failure."""
    if _number(row.get("composite")) is None:
        return ["composite"]
    return [str(rule["id"]) for rule in register["screen"]["hardFilters"] if not _rule(row, rule)]


def passes(row: dict[str, Any], register: dict[str, Any]) -> bool:
    """True when the row has a composite and meets every hard filter."""
    return not failed_filters(row, register)


def shortlist(rows: list[dict[str, Any]], register: dict[str, Any]) -> list[dict[str, Any]]:
    """The highest composites that pass, at most ``shortlistSize``, name as the tie break."""
    kept = [row for row in rows if passes(row, register)]
    kept.sort(key=lambda row: (-float(row["composite"]), str(row.get("symbol") or "")))
    return kept[: int(register["screen"]["shortlistSize"])]


def _rule(row: dict[str, Any], rule: dict[str, Any]) -> bool:
    value = _number(row.get(rule["field"]))
    if value is None and rule.get("passWhenNetCash"):
        net = _net_debt(row)
        return net is not None and net <= 0
    if value is None:
        return False
    return bool(_OPS[str(rule["op"])](value, float(rule["value"])))


def _net_debt(row: dict[str, Any]) -> float | None:
    long_debt = _number(row.get("longTermDebt"))
    short_debt = _number(row.get("shortTermDebt"))
    cash = _number(row.get("cash"))
    if long_debt is None or short_debt is None or cash is None:
        return None
    return long_debt + short_debt - cash


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
