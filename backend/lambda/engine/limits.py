"""Checks that nothing else may weaken. A buy cannot leave exposure above the cap."""

from __future__ import annotations

from typing import Any

HARD_LEVERAGE_CAP = 1.5
_ROUNDING = 0.005


def check_batch(
    equity: float,
    positions: dict[str, float],
    orders: list[dict[str, Any]],
    prices: dict[str, float],
    register: dict[str, Any],
    target_level: float,
    *,
    universe: set[str],
    sectors: dict[str, str],
    buys_halted: bool,
) -> list[str]:
    """Violations of the portfolio as it would be after every order fills.

    ``positions`` and order quantities are share counts. Sells-only batches
    are not blocked for still being above the cap.
    """
    violations: list[str] = []
    if equity <= 0:
        return ["equity_not_positive"]
    resulting = dict(positions)
    for order in orders:
        symbol = str(order["symbol"])
        quantity = float(order["quantity"])
        signed = quantity if order["side"] == "buy" else -quantity
        resulting[symbol] = resulting.get(symbol, 0) + signed
        if not order.get("thesisId"):
            violations.append(f"missing_thesis:{symbol}")
        price = prices.get(symbol)
        if price is None:
            violations.append(f"missing_price:{symbol}")
            continue
        if quantity * price / equity > float(register["execution"]["maxOrderWeight"]):
            violations.append(f"order_too_large:{symbol}")
        if order["side"] == "buy" and symbol not in universe:
            violations.append(f"outside_universe:{symbol}")
    if any(quantity < -1e-9 for quantity in resulting.values()):
        violations.append("negative_quantity")
    if len(orders) > int(register["execution"]["maxOrdersPerDay"]):
        violations.append("too_many_orders")
    has_buy = any(order["side"] == "buy" for order in orders)
    if has_buy and buys_halted:
        violations.append("buys_halted")
    if not has_buy:
        return violations
    cap = min(float(target_level), float(register["leverage"]["hardCap"]), HARD_LEVERAGE_CAP)
    gross = 0.0
    by_sector: dict[str, float] = {}
    for symbol, quantity in resulting.items():
        if quantity <= 0:
            continue
        price = prices.get(symbol)
        if price is None:
            continue
        value = quantity * price
        gross += value
        by_sector[sectors.get(symbol, "")] = by_sector.get(sectors.get(symbol, ""), 0.0) + value
    if gross / equity > cap + _ROUNDING:
        violations.append("exposure")
    hard = float(register["portfolio"]["maxPositionWeightHard"])
    for symbol, quantity in resulting.items():
        price = prices.get(symbol)
        if quantity > 0 and price is not None and quantity * price / equity > hard + _ROUNDING:
            violations.append(f"position:{symbol}")
    sector_cap = float(register["portfolio"]["maxSectorWeight"]) * float(target_level)
    for sector, value in by_sector.items():
        if value / equity > sector_cap + _ROUNDING:
            violations.append(f"sector:{sector}")
    return violations
