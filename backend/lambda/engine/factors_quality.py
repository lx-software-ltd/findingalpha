"""Quality factors. Missing inputs return None. Thresholds come from the caller."""

from __future__ import annotations


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _average_invested_capital(snapshot: dict) -> float | None:
    equity = _num(snapshot.get("equity_avg"))
    long_debt = _num(snapshot.get("longTermDebt_avg"))
    short_debt = _num(snapshot.get("shortTermDebt_avg"))
    cash = _num(snapshot.get("cash_avg"))
    if equity is None or long_debt is None or short_debt is None or cash is None:
        return None
    return equity + long_debt + short_debt - cash


def _latest_debt(snapshot: dict) -> float | None:
    long_debt = _num(snapshot.get("longTermDebt"))
    short_debt = _num(snapshot.get("shortTermDebt"))
    if long_debt is None or short_debt is None:
        return None
    return long_debt + short_debt


def roic(snapshot: dict, params: dict) -> float | None:
    """NOPAT_ttm / average(investedCapital)."""
    operating = _num(snapshot.get("operatingIncome_ttm"))
    invested = _average_invested_capital(snapshot)
    if operating is None or not invested:
        return None
    pretax = _num(snapshot.get("pretaxIncome_ttm"))
    tax = _num(snapshot.get("incomeTax_ttm"))
    if pretax is None or pretax <= 0 or tax is None:
        rate = float(params["defaultTaxRate"])
    else:
        rate = min(max(tax / pretax, 0), float(params["maxTaxRate"]))
    return operating * (1 - rate) / invested


roic.required_parameters = ("maxTaxRate", "defaultTaxRate")


def gross_profitability(snapshot: dict, _params: dict) -> float | None:
    """grossProfit_ttm / avg(totalAssets). If grossProfit is missing use revenue_ttm - costOfRevenue_ttm."""
    profit = _num(snapshot.get("grossProfit_ttm"))
    if profit is None:
        revenue = _num(snapshot.get("revenue_ttm"))
        cost = _num(snapshot.get("costOfRevenue_ttm"))
        if revenue is None or cost is None:
            return None
        profit = revenue - cost
    assets = _num(snapshot.get("totalAssets_avg"))
    if not assets:
        return None
    return profit / assets


def free_cash_flow_ttm(snapshot: dict, _params: dict) -> float | None:
    """operatingCashFlow_ttm - capex_ttm."""
    operating = _num(snapshot.get("operatingCashFlow_ttm"))
    capex = _num(snapshot.get("capex_ttm"))
    if operating is None or capex is None:
        return None
    return operating - capex


def fcf_margin(snapshot: dict, params: dict) -> float | None:
    """(operatingCashFlow_ttm - capex_ttm) / revenue_ttm."""
    flow = free_cash_flow_ttm(snapshot, params)
    revenue = _num(snapshot.get("revenue_ttm"))
    if flow is None or not revenue:
        return None
    return flow / revenue


def accruals(snapshot: dict, _params: dict) -> float | None:
    """(netIncome_ttm - operatingCashFlow_ttm) / avg(totalAssets)."""
    income = _num(snapshot.get("netIncome_ttm"))
    operating = _num(snapshot.get("operatingCashFlow_ttm"))
    assets = _num(snapshot.get("totalAssets_avg"))
    if income is None or operating is None or not assets:
        return None
    return (income - operating) / assets


def net_debt_to_ebitda(snapshot: dict, _params: dict) -> float | None:
    """(longTermDebt + shortTermDebt - cash) / (operatingIncome_ttm + depreciationAmortization_ttm)."""
    long_debt = _num(snapshot.get("longTermDebt"))
    short_debt = _num(snapshot.get("shortTermDebt"))
    cash = _num(snapshot.get("cash"))
    operating = _num(snapshot.get("operatingIncome_ttm"))
    depreciation = _num(snapshot.get("depreciationAmortization_ttm"))
    if None in (long_debt, short_debt, cash, operating, depreciation):
        return None
    assert long_debt is not None and short_debt is not None and cash is not None
    assert operating is not None and depreciation is not None
    ebitda = operating + depreciation
    if ebitda <= 0:
        return None
    return (long_debt + short_debt - cash) / ebitda


def interest_coverage(snapshot: dict, params: dict) -> float | None:
    """operatingIncome_ttm / interestExpense_ttm, capped at coverageCap."""
    operating = _num(snapshot.get("operatingIncome_ttm"))
    if operating is None:
        return None
    interest = _num(snapshot.get("interestExpense_ttm"))
    debt = _latest_debt(snapshot)
    cap = float(params["coverageCap"])
    if not interest:
        if debt == 0:
            return cap
        return None
    return min(operating / interest, cap)


interest_coverage.required_parameters = ("coverageCap",)
