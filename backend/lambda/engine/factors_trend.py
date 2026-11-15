"""Trend factors from adjusted closes. Index t is the screen date."""

from __future__ import annotations

import math


def momentum_12_1(closes: list[float | None]) -> float | None:
    """close[t-21] / close[t-252] - 1. ``closes`` ends at t."""
    if len(closes) < 253:
        return None
    recent = closes[-22]
    past = closes[-253]
    if recent is None or past is None or past == 0:
        return None
    return recent / past - 1


def above_sma200(closes: list[float | None]) -> float | None:
    """close[t] / mean(close[t-199..t]) - 1."""
    window = closes[-200:]
    if len(window) < 200 or any(value is None for value in window):
        return None
    numbers = [float(value) for value in window if value is not None]
    mean = sum(numbers) / len(numbers)
    last = numbers[-1]
    if mean == 0:
        return None
    return last / mean - 1


def volatility_252(closes: list[float | None]) -> float | None:
    """Annualised standard deviation of 252 daily log returns."""
    window = closes[-253:]
    if len(window) < 253 or any(value is None or value <= 0 for value in window):
        return None
    numbers = [float(value) for value in window if value is not None]
    logs = [math.log(numbers[index] / numbers[index - 1]) for index in range(1, len(numbers))]
    mean = sum(logs) / len(logs)
    variance = sum((value - mean) ** 2 for value in logs) / len(logs)
    return math.sqrt(variance) * math.sqrt(252)
