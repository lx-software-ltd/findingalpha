"""One company at a time for the universe build.

The raw facts are not kept. A later run continues from the saved company.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

import share_count
import universe
import universe_data

Facts = Callable[[str], list[dict[str, Any]] | None]
Probe = Callable[[str], bool]
Submissions = Callable[[str], dict[str, Any]]
Cover = Callable[[str, date], dict[str, Any] | None]
_GATES = ("fundamentals", "sic", "annualReport", "history")
_BATCH = 100


def collect(
    companies: list[dict[str, Any]],
    day: date,
    rules: dict[str, Any],
    context: Any,
    *,
    facts_of: Facts,
    probe: Probe | None,
    subs_of: Submissions,
    cover_of: Cover,
    bucket: str,
    client: Any,
    allow_refresh: bool = True,
) -> dict[str, Any]:
    """The small records that passed the fact rules, or a reason to stop."""
    if not companies:
        universe_data.clear_build_progress(day, bucket, client)
        return _ready([], _blank())
    ciks = [str(row["cik"]) for row in companies]
    saved = _saved(day, ciks, bucket, client) if allow_refresh else {}
    if probe is not None and allow_refresh and saved.get("phase") != "qualify":
        stopped = _exists(companies, day, ciks, context, probe, saved, bucket, client)
        if stopped is not None:
            return stopped
        saved = {}
    return _qualify(
        companies,
        day,
        rules,
        context,
        facts_of=facts_of,
        subs_of=subs_of,
        cover_of=cover_of,
        bucket=bucket,
        client=client,
        allow_refresh=allow_refresh,
        saved=saved,
        ciks=ciks,
    )


def _blank() -> dict[str, int]:
    return {gate: 0 for gate in _GATES}


def _ready(prepared: list[tuple[dict[str, Any], share_count.Chosen]], counts: dict[str, int]) -> dict[str, Any]:
    return {"status": "ready", "prepared": prepared, "counts": counts, "pending": 0, "missing": []}


def _running(pending: int) -> dict[str, Any]:
    return {"status": "running", "pending": pending, "missing": [], "prepared": [], "counts": _blank()}


def _saved(day: date, ciks: list[str], bucket: str, client: Any) -> dict[str, Any]:
    found = universe_data.read_build_progress(day, bucket, client) or {}
    if found.get("ciks") != ciks:
        return {}
    return found


def _counts(saved: dict[str, Any]) -> dict[str, int]:
    raw = saved.get("counts") if isinstance(saved.get("counts"), dict) else {}
    return {gate: int(raw.get(gate) or 0) for gate in _GATES}


def _unpack(saved: dict[str, Any]) -> list[tuple[dict[str, Any], share_count.Chosen]]:
    prepared: list[tuple[dict[str, Any], share_count.Chosen]] = []
    for item in saved.get("prepared") or []:
        if not isinstance(item, dict):
            raise ValueError("progress row")
        prepared.append(
            (
                {
                    "symbol": str(item["symbol"]),
                    "cik": str(item["cik"]),
                    "name": str(item.get("name") or ""),
                    "close": float(item["close"]),
                    "medianDollarVolume": float(item["medianDollarVolume"]),
                    "sic": None if item.get("sic") is None else str(item["sic"]),
                },
                share_count.Chosen(
                    float(item["shares"]),
                    date.fromisoformat(str(item["end"])[:10]),
                    date.fromisoformat(str(item["after"])[:10]),
                    str(item["source"]),
                ),
            )
        )
    return prepared


def _pack(row: dict[str, Any], picked: share_count.Chosen) -> dict[str, Any]:
    return {
        "symbol": row["symbol"],
        "cik": row["cik"],
        "name": row["name"],
        "close": row["close"],
        "medianDollarVolume": row["medianDollarVolume"],
        "sic": row["sic"],
        "shares": picked.value,
        "end": picked.end.isoformat(),
        "after": picked.after.isoformat(),
        "source": picked.source,
    }


def _write(
    day: date,
    ciks: list[str],
    phase: str,
    cursor: int,
    missing: list[str],
    counts: dict[str, int],
    prepared: list[tuple[dict[str, Any], share_count.Chosen]],
    bucket: str,
    client: Any,
) -> None:
    universe_data.write_build_progress(
        day,
        {
            "ciks": ciks,
            "phase": phase,
            "cursor": cursor,
            "missing": missing,
            "counts": counts,
            "prepared": [_pack(row, picked) for row, picked in prepared],
        },
        bucket,
        client,
    )


def _exists(
    companies: list[dict[str, Any]],
    day: date,
    ciks: list[str],
    context: Any,
    probe: Probe,
    saved: dict[str, Any],
    bucket: str,
    client: Any,
) -> dict[str, Any] | None:
    """Missing files, without their bodies. ``None`` means every file is there."""
    cursor = int(saved.get("cursor") or 0) if saved.get("phase") == "exists" else 0
    missing = [str(cik) for cik in saved.get("missing") or []] if saved.get("phase") == "exists" else []
    for index, row in enumerate(companies):
        if index < cursor:
            continue
        if universe._out_of_time(context):
            _write(day, ciks, "exists", index, missing, _blank(), [], bucket, client)
            return _running(len(companies) - index)
        if not probe(str(row["cik"])):
            missing.append(str(row["cik"]))
        if (index + 1) % _BATCH == 0:
            _write(day, ciks, "exists", index + 1, missing, _blank(), [], bucket, client)
    if not missing:
        universe_data.clear_build_progress(day, bucket, client)
        return None
    universe_data.clear_build_progress(day, bucket, client)
    return {
        "status": "refresh",
        "missing": missing,
        "pending": len(missing),
        "prepared": [],
        "counts": _blank(),
    }


def _qualify(
    companies: list[dict[str, Any]],
    day: date,
    rules: dict[str, Any],
    context: Any,
    *,
    facts_of: Facts,
    subs_of: Submissions,
    cover_of: Cover,
    bucket: str,
    client: Any,
    allow_refresh: bool,
    saved: dict[str, Any],
    ciks: list[str],
) -> dict[str, Any]:
    qualify = saved.get("phase") == "qualify"
    try:
        prepared = _unpack(saved) if qualify else []
        counts = _counts(saved) if qualify else _blank()
    except (KeyError, TypeError, ValueError):
        prepared = []
        counts = _blank()
        qualify = False
    cursor = int(saved.get("cursor") or 0) if qualify else 0
    missing = [str(cik) for cik in saved.get("missing") or []] if qualify else []
    form = str(rules["requireAnnualReportForm"])
    max_age = int(rules["maxAnnualReportAgeDays"])
    min_years = int(rules["minFundamentalsYears"])

    def remember(at: int) -> None:
        _write(day, ciks, "qualify", at, missing, counts, prepared, bucket, client)

    for index, row in enumerate(companies):
        if index < cursor:
            continue
        if universe._out_of_time(context):
            remember(index)
            return _running(len(companies) - index)
        facts = facts_of(str(row["cik"]))
        if facts is None:
            if allow_refresh:
                missing.append(str(row["cik"]))
            continue
        if missing and allow_refresh:
            del facts
            continue
        outcome = _assess(row, facts, day, rules, form, max_age, min_years, subs_of, cover_of, context)
        del facts
        if outcome[0] == "pause":
            remember(index)
            return _running(len(companies) - index)
        if outcome[0] == "drop":
            if (index + 1) % _BATCH == 0:
                remember(index + 1)
            continue
        for gate in outcome[1]:
            counts[gate] += 1
        if outcome[0] == "in":
            prepared.append((outcome[2], outcome[3]))
        if (index + 1) % _BATCH == 0:
            remember(index + 1)
    if missing and allow_refresh:
        universe_data.clear_build_progress(day, bucket, client)
        return {
            "status": "refresh",
            "missing": missing,
            "pending": len(missing),
            "prepared": [],
            "counts": _blank(),
        }
    universe_data.clear_build_progress(day, bucket, client)
    return _ready(prepared, counts)


def _assess(
    row: dict[str, Any],
    facts: list[dict[str, Any]],
    day: date,
    rules: dict[str, Any],
    form: str,
    max_age: int,
    min_years: int,
    subs_of: Submissions,
    cover_of: Cover,
    context: Any,
) -> tuple[str, tuple[str, ...], dict[str, Any], share_count.Chosen]:
    """How far one company gets. The facts list is not part of the result."""
    visible = universe._visible(facts, day)
    if not visible:
        return ("drop", (), {}, share_count.Chosen(0, day, day, ""))
    if universe._out_of_time(context):
        return ("pause", (), {}, share_count.Chosen(0, day, day, ""))
    sic = subs_of(str(row["cik"])).get("sic")
    passed = ["fundamentals"]
    if universe._excluded(sic, rules["excludeSicRanges"]):
        return ("out", tuple(passed), {}, share_count.Chosen(0, day, day, ""))
    passed.append("sic")
    if not universe._recent_annual(visible, form, day, max_age):
        return ("out", tuple(passed), {}, share_count.Chosen(0, day, day, ""))
    passed.append("annualReport")
    if len(set(universe._annual_filings(visible, form).values())) < min_years:
        return ("out", tuple(passed), {}, share_count.Chosen(0, day, day, ""))
    passed.append("history")
    picked = share_count.choose(visible, day)
    del visible
    if picked is None:
        if universe._out_of_time(context):
            return ("pause", (), {}, share_count.Chosen(0, day, day, ""))
        picked = share_count.from_cover(cover_of(str(row["cik"]), day), day)
    if picked is None:
        return ("out", tuple(passed), {}, share_count.Chosen(0, day, day, ""))
    carried = {
        "symbol": row["symbol"],
        "cik": row["cik"],
        "name": row["name"],
        "close": row["close"],
        "medianDollarVolume": row["medianDollarVolume"],
        "sic": sic,
    }
    return ("in", tuple(passed), carried, picked)
