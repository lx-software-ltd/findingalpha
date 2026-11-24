"""Winsorise, standardise within sector, and combine group scores."""

from __future__ import annotations

import math
from typing import Any

from methodology import register_hash


def winsorise(values: list[float | None], std_devs: float) -> list[float | None]:
    """Clip present values to the mean ± ``std_devs`` population standard deviations.

    The deviation is taken across the values that are present. Missing values stay missing.
    """
    present = [value for value in values if value is not None]
    if not present:
        return list(values)
    mean = _mean(present)
    deviation = _population_std(present)
    low = mean - std_devs * deviation
    high = mean + std_devs * deviation
    return [None if value is None else min(max(value, low), high) for value in values]


def _uses_universe(sector: str) -> bool:
    """A blank sector and the unmapped sector ``Other`` are not a peer group."""
    return not str(sector).strip() or str(sector).strip() == "Other"


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
    """Z-score inside the sector. A blank sector, a small sector, or a zero deviation uses the universe."""
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
        if _uses_universe(sector) or len(pool) < min_sector_size or _population_std(pool) == 0:
            pool = universe
        deviation = _population_std(pool)
        if deviation == 0:
            out.append(0)
            continue
        out.append((value - _mean(pool)) / deviation)
    return out


def zscores_within_sector(rows: list[dict[str, Any]], factor_id: str, min_sector_size: int) -> list[float | None]:
    """Z-scores of one factor column."""
    return zscores(
        [row.get(factor_id) for row in rows],
        [str(row.get("sector") or "") for row in rows],
        min_sector_size=min_sector_size,
    )


def group_score(factor_scores: list[float | None], *, min_share: float) -> float | None:
    """Mean of the present scores, or None when too many are missing."""
    present = [score for score in factor_scores if score is not None]
    if not factor_scores or len(present) / len(factor_scores) < min_share:
        return None
    return _mean(present)


def group_scores(row: dict[str, Any], factors: list[dict[str, Any]], *, min_share: float) -> dict[str, float | None]:
    """One score per group from the row's ``z`` map."""
    grouped: dict[str, list[str]] = {}
    for factor in factors:
        grouped.setdefault(str(factor["group"]), []).append(str(factor["id"]))
    raw_scores = row.get("z")
    scores = raw_scores if isinstance(raw_scores, dict) else {}
    return {
        name: group_score([scores.get(factor_id) for factor_id in ids], min_share=min_share)
        for name, ids in grouped.items()
    }


def _combine(groups: dict[str, float | None], weights: dict[str, float]) -> float | None:
    if any(groups.get(name) is None for name in weights):
        return None
    if not weights:
        return 0
    total = 0.0
    for name in weights:
        score = groups[name]
        assert score is not None  # nosec B101
        total += float(weights[name]) * float(score)
    return total


def composite(rows: list[dict[str, Any]], register: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach z-scores, group scores, the composite, and the register hash.

    Factors whose group is outside ``groupWeights`` stay on the row and
    do not enter the score. A missing group score makes the composite None.
    """
    spec = register["composite"]
    weights = spec["groupWeights"]
    factors = [factor for factor in register["factors"] if factor.get("group") in weights]
    std_devs = float(spec["winsoriseStdDevs"])
    min_sector = int(spec["minSectorSize"])
    min_share = float(spec["minFactorsPerGroupShare"])
    sectors = [str(row.get("sector") or "") for row in rows]
    signed: dict[str, list[float | None]] = {}
    for factor in factors:
        clipped = winsorise([row.get(factor["id"]) for row in rows], std_devs)
        scores = zscores(clipped, sectors, min_sector_size=min_sector)
        sign = -1 if factor.get("direction") == "lower" else 1
        signed[str(factor["id"])] = [None if score is None else sign * score for score in scores]
    digest = register_hash(register)
    scored_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        z = {factor_id: values[index] for factor_id, values in signed.items()}
        groups = group_scores({"z": z}, factors, min_share=min_share)
        scored = dict(row)
        scored["z"] = z
        scored["groups"] = {name: groups.get(name) for name in weights}
        scored["composite"] = _combine(scored["groups"], weights)
        scored["registerHash"] = digest
        scored_rows.append(scored)
    return scored_rows
