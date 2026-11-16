"""Value factors. Enterprise value must be positive."""

from __future__ import annotations

import factors_quality


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def earnings_yield(snapshot: dict, _params: dict) -> float | None:
    """operatingIncome_ttm / enterpriseValue."""
    operating = _num(snapshot.get("operatingIncome_ttm"))
    value = _num(snapshot.get("enterpriseValue"))
    if operating is None or value is None or value <= 0:
        return None
    return operating / value


def fcf_yield(snapshot: dict, params: dict) -> float | None:
    """(operatingCashFlow_ttm - capex_ttm) / enterpriseValue."""
    flow = factors_quality.free_cash_flow_ttm(snapshot, params)
    value = _num(snapshot.get("enterpriseValue"))
    if flow is None or value is None or value <= 0:
        return None
    return flow / value
