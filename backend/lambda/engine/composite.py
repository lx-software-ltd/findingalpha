"""Winsorise, standardise within sector, and combine group scores."""

from __future__ import annotations

import math
from typing import Any


def _percentile(sorted_values: list[float], percent: float) -> float:
    if not sorted_values:
        raise ValueError("empty")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (percent / 100) * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[low]
    weight = rank - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def winsorise(values: list[float | None], low_percent: float, high_percent: float) -> list[float | None]:
    present = sorted(value for value in values if value is not None)
    if not present:
        return list(values)
    low = _percentile(present, low_percent)
    high = _percentile(present, high_percent)
    return [None if value is None else min(max(value, low), high) for value in values]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _population_std(values: list[float]) -> float:
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def zscores(
    values: list[float | None],
    sectors: list[str],
    *,
    min_sector_size: int,
) -> list[float | None]:
    """Z-score inside the sector, falling back to the universe when the sector is too small."""
    by_sector: dict[str, list[float]] = {}
    for value, sector in zip(values, sectors, strict=True):
        if value is not None:
            by_sector.setdefault(sector, []).append(value)
    universe = [value for value in values if value is not None]
    out: list[float | None] = []
    for value, sector in zip(values, sectors, strict=True):
        if value is None:
            out.append(None)
            continue
        pool = by_sector.get(sector, [])
        if len(pool) < min_sector_size or _population_std(pool) == 0:
            pool = universe
        deviation = _population_std(pool)
        if deviation == 0:
            out.append(0.0)
            continue
        out.append((value - _mean(pool)) / deviation)
    return out


def group_score(factor_scores: list[float | None], *, min_share: float) -> float | None:
    present = [score for score in factor_scores if score is not None]
    if not factor_scores or len(present) / len(factor_scores) < min_share:
        return None
    return _mean(present)


def composite(groups: dict[str, float | None], weights: dict[str, float]) -> float | None:
    if any(groups.get(name) is None for name in weights):
        return None
    return sum(weights[name] * float(groups[name]) for name in weights)


def score_universe(
    rows: list[dict[str, Any]],
    factors: list[dict[str, Any]],
    *,
    composite_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach winsorised z-scores and a composite to each row. Rows need ``sector`` and factor ids."""
    low, high = composite_spec["winsorisePercentiles"]
    min_sector = int(composite_spec["minSectorSize"])
    min_share = float(composite_spec["minFactorsPerGroupShare"])
    weights = composite_spec["groupWeights"]
    sectors = [str(row["sector"]) for row in rows]
    signed: dict[str, list[float | None]] = {}
    for factor in factors:
        raw = [row.get(factor["id"]) for row in rows]
        clipped = winsorise(raw, low, high)
        scores = zscores(clipped, sectors, min_sector_size=min_sector)
        sign = -1 if factor["direction"] == "lower" else 1
        signed[factor["id"]] = [None if score is None else sign * score for score in scores]
    groups: dict[str, list[str]] = {}
    for factor in factors:
        groups.setdefault(factor["group"], []).append(factor["id"])
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        group_values = {
            name: group_score([signed[factor_id][index] for factor_id in ids], min_share=min_share)
            for name, ids in groups.items()
        }
        scored = dict(row)
        scored["groups"] = group_values
        scored["composite"] = composite(group_values, weights)
        out.append(scored)
    return out
