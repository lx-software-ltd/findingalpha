"""Quality factors. Missing inputs return None. Thresholds come from the caller."""

from __future__ import annotations


def _need(*values: float | None) -> bool:
    return all(value is not None for value in values)


def roic(
    operating_income_ttm: float | None,
    income_tax_ttm: float | None,
    pretax_income_ttm: float | None,
    invested_capital: float | None,
    *,
    max_tax_rate: float,
    default_tax_rate: float,
) -> float | None:
    if not _need(operating_income_ttm, invested_capital) or not invested_capital:
        return None
    if pretax_income_ttm is None or pretax_income_ttm <= 0 or income_tax_ttm is None:
        tax_rate = default_tax_rate
    else:
        tax_rate = min(max(income_tax_ttm / pretax_income_ttm, 0.0), max_tax_rate)
    assert operating_income_ttm is not None and invested_capital is not None
    return operating_income_ttm * (1 - tax_rate) / invested_capital


def gross_profitability(
    gross_profit_ttm: float | None,
    revenue_ttm: float | None,
    cost_of_revenue_ttm: float | None,
    average_assets: float | None,
) -> float | None:
    profit = gross_profit_ttm
    if profit is None and _need(revenue_ttm, cost_of_revenue_ttm):
        assert revenue_ttm is not None and cost_of_revenue_ttm is not None
        profit = revenue_ttm - cost_of_revenue_ttm
    if profit is None or not average_assets:
        return None
    return profit / average_assets


def fcf_margin(operating_cash_flow_ttm: float | None, capex_ttm: float | None, revenue_ttm: float | None) -> float | None:
    if not _need(operating_cash_flow_ttm, capex_ttm, revenue_ttm) or not revenue_ttm:
        return None
    assert operating_cash_flow_ttm is not None and capex_ttm is not None and revenue_ttm is not None
    return (operating_cash_flow_ttm - capex_ttm) / revenue_ttm


def accruals(
    net_income_ttm: float | None,
    operating_cash_flow_ttm: float | None,
    average_assets: float | None,
) -> float | None:
    if not _need(net_income_ttm, operating_cash_flow_ttm) or not average_assets:
        return None
    assert net_income_ttm is not None and operating_cash_flow_ttm is not None and average_assets is not None
    return (net_income_ttm - operating_cash_flow_ttm) / average_assets


def net_debt_to_ebitda(
    long_term_debt: float | None,
    short_term_debt: float | None,
    cash: float | None,
    operating_income_ttm: float | None,
    depreciation_ttm: float | None,
) -> float | None:
    if not _need(long_term_debt, short_term_debt, cash, operating_income_ttm, depreciation_ttm):
        return None
    assert None not in (long_term_debt, short_term_debt, cash, operating_income_ttm, depreciation_ttm)
    denominator = operating_income_ttm + depreciation_ttm  # type: ignore[operator]
    if denominator <= 0:
        return None
    return (long_term_debt + short_term_debt - cash) / denominator  # type: ignore[operator]


def interest_coverage(
    operating_income_ttm: float | None,
    interest_expense_ttm: float | None,
    debt: float | None,
    *,
    coverage_cap: float,
) -> float | None:
    if operating_income_ttm is None:
        return None
    if not interest_expense_ttm:
        if debt == 0:
            return coverage_cap
        return None
    return min(operating_income_ttm / interest_expense_ttm, coverage_cap)


def free_cash_flow_ttm(operating_cash_flow_ttm: float | None, capex_ttm: float | None) -> float | None:
    if not _need(operating_cash_flow_ttm, capex_ttm):
        return None
    assert operating_cash_flow_ttm is not None and capex_ttm is not None
    return operating_cash_flow_ttm - capex_ttm
