"""Performance figures for a monthly equity curve. Each function is pure."""

from __future__ import annotations

import math
from typing import Any


def cagr(curve: list[float], months: int | None = None) -> float | None:
    """``(end / start) ** (12 / months) - 1``. ``curve`` includes the starting 100.

    ``months`` is the calendar span. Without it, each step of ``curve`` is one month.
    """
    steps = len(curve) - 1 if months is None else months
    if steps < 1 or curve[0] <= 0 or curve[-1] <= 0:
        return None
    return (curve[-1] / curve[0]) ** (12 / steps) - 1


def annualised_volatility(period_returns: list[float]) -> float | None:
    """Population standard deviation of the monthly returns, times ``sqrt(12)``."""
    if not period_returns:
        return None
    return _population_std(period_returns) * math.sqrt(12)


def sharpe(period_returns: list[float], cash_returns: list[float]) -> float | None:
    """Mean excess return over its population deviation, times ``sqrt(12)``."""
    excess = [left - right for left, right in zip(period_returns, cash_returns, strict=True)]
    if not excess:
        return None
    deviation = _population_std(excess)
    if deviation == 0:
        return None
    return (_mean(excess) / deviation) * math.sqrt(12)


def max_drawdown(curve: list[float], labels: list[str]) -> dict[str, Any]:
    """Largest fall from a previous high, as a negative fraction, with the two labels."""
    peak = curve[0]
    peak_at = 0
    worst = 0.0
    start = labels[0]
    end = labels[0]
    for index, value in enumerate(curve):
        if value >= peak:
            peak = value
            peak_at = index
        if peak <= 0:
            continue
        drop = value / peak - 1
        if drop < worst:
            worst = drop
            start = labels[peak_at]
            end = labels[index]
    return {"drawdown": worst, "start": start, "end": end}


def hit_rate(left: list[float], right: list[float]) -> float | None:
    """Share of periods where ``left`` beat ``right``."""
    if not left:
        return None
    wins = sum(1 for first, second in zip(left, right, strict=True) if first > second)
    return wins / len(left)


def worst_window(curve: list[float], labels: list[str], months: int = 12) -> dict[str, Any] | None:
    """The lowest return over a span of ``months`` steps."""
    if months < 1 or len(curve) <= months:
        return None
    worst: float | None = None
    start = labels[0]
    end = labels[0]
    for index in range(len(curve) - months):
        if curve[index] <= 0:
            continue
        change = curve[index + months] / curve[index] - 1
        if worst is None or change < worst:
            worst = change
            start = labels[index]
            end = labels[index + months]
    if worst is None:
        return None
    return {"return": worst, "start": start, "end": end}


def average_turnover(turnovers: list[float]) -> float | None:
    if not turnovers:
        return None
    return _mean(turnovers)


def yearly_cost_drag(turnovers: list[float], cost_bps: float) -> float | None:
    """Average one-way turnover, charged on both sides, times twelve."""
    if not turnovers:
        return None
    return _mean(turnovers) * 2 * cost_bps / 10000 * 12


def longest_behind(strategy: list[float], benchmark: list[float], labels: list[str]) -> dict[str, Any]:
    """Longest run of months where strategy wealth lags the benchmark since a relative high.

    The relative line is strategy divided by the benchmark. A new high resets the stretch.
    """
    if not labels or len(strategy) != len(benchmark) or len(strategy) != len(labels):
        return {"months": 0, "start": "", "end": ""}
    peak = _relative(strategy[0], benchmark[0])
    peak_at = 0
    best = 0
    start = labels[0]
    end = labels[0]
    for index in range(1, len(strategy)):
        relative = _relative(strategy[index], benchmark[index])
        if relative >= peak:
            peak = relative
            peak_at = index
            continue
        span = index - peak_at
        if span > best:
            best = span
            start = labels[peak_at]
            end = labels[index]
    return {"months": best, "start": start, "end": end}


def yearly_table(curve: list[float], other: list[float], labels: list[str]) -> list[dict[str, Any]]:
    """Calendar-year returns. A year uses the last point of the previous year as its base."""
    last: dict[str, int] = {}
    for index, label in enumerate(labels):
        year = str(label)[:4]
        if year.isdigit():
            last[year] = index
    table: list[dict[str, Any]] = []
    base = 0
    for year in sorted(last):
        end = last[year]
        table.append({"year": year, "strategy": _change(curve, base, end), "benchmark": _change(other, base, end)})
        base = end
    return table


def _change(curve: list[float], start: int, end: int) -> float | None:
    if curve[start] <= 0:
        return None
    return curve[end] / curve[start] - 1


def _relative(strategy: float, benchmark: float) -> float:
    if benchmark == 0:
        return 0.0
    return strategy / benchmark


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _population_std(values: list[float]) -> float:
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
