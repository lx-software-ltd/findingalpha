"""Value factors. Enterprise value must be positive."""

from __future__ import annotations


def enterprise_value(
    market_cap: float | None,
    long_term_debt: float | None,
    short_term_debt: float | None,
    cash: float | None,
) -> float | None:
    if None in (market_cap, long_term_debt, short_term_debt, cash):
        return None
    assert market_cap is not None and long_term_debt is not None and short_term_debt is not None and cash is not None
    value = market_cap + long_term_debt + short_term_debt - cash
    if value <= 0:
        return None
    return value


def earnings_yield(operating_income_ttm: float | None, value: float | None) -> float | None:
    if operating_income_ttm is None or not value:
        return None
    return operating_income_ttm / value


def fcf_yield(free_cash_flow: float | None, value: float | None) -> float | None:
    if free_cash_flow is None or not value:
        return None
    return free_cash_flow / value
