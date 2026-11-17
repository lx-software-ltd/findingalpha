"""One company at a time for the universe build.

The raw facts are not kept. A later run continues from the saved company
and the company list stored with it.
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
Actions = Callable[[date], list[dict[str, Any]]]
_GATES = ("fundamentals", "sic", "annualReport", "history")
_FUNNEL = ("assets", "withCik", "price", "dollarVolume")
_BATCH = 100


def published(day: date, bucket: str, client: Any) -> dict[str, Any] | None:
    """The result saved after the members file was written."""
    found = universe_data.read_build_progress(day, bucket, client) or {}
    result = found.get("result")
    if found.get("phase") == "written" and isinstance(result, dict):
        return dict(result)
    return None


def saved_liquid(day: date, bucket: str, client: Any) -> dict[str, Any] | None:
    """The company list from a build that has not been written yet."""
    found = universe_data.read_build_progress(day, bucket, client) or {}
    if found.get("phase") not in {"exists", "qualify"}:
        return None
    rows = found.get("companies")
    if not isinstance(rows, list):
        return None
    companies = [dict(row) for row in rows if isinstance(row, dict)]
    if not companies:
        return None
    raw = found.get("funnel") if isinstance(found.get("funnel"), dict) else {}
    funnel = {key: int(raw.get(key) or 0) for key in _FUNNEL}
    text = str(found.get("priceAsOf") or "")
    price_as_of = date.fromisoformat(text[:10]) if text else None
    return {"companies": companies, "funnel": funnel, "priceAsOf": price_as_of}


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
    funnel: dict[str, int] | None = None,
    price_as_of: date | None = None,
) -> dict[str, Any]:
    """The small records that passed the fact rules, or a reason to stop."""
    kept = dict(funnel or {})
    if not companies:
        universe_data.clear_build_progress(day, bucket, client)
        return _ready([], _blank())
    ciks = [str(row["cik"]) for row in companies]
    saved = _saved(day, ciks, bucket, client) if allow_refresh else {}
    if probe is not None and allow_refresh and saved.get("phase") != "qualify":
        stopped = _exists(companies, day, ciks, context, probe, saved, kept, price_as_of, bucket, client)
        if stopped is not None:
            return stopped
        saved = {}
    return _qualify(
        companies,
        day,
        rules,
        context,
        facts_of=facts_of,
        probe=probe,
        subs_of=subs_of,
        cover_of=cover_of,
        bucket=bucket,
        client=client,
        allow_refresh=allow_refresh,
        saved=saved,
        ciks=ciks,
        funnel=kept,
        price_as_of=price_as_of,
    )


def publish(
    prepared: list[tuple[dict[str, Any], share_count.Chosen]],
    stage: dict[str, int],
    funnel: dict[str, int],
    day: date,
    rules: dict[str, Any],
    sessions: list[date],
    read_actions: Actions | None,
    bucket: str,
    client: Any,
    ranges: list[dict[str, Any]],
    company_sectors: dict[str, str],
    price_as_of: date | None,
) -> dict[str, Any]:
    """Write the members, then keep a short marker so a retry skips this work."""
    earliest: date | None = None
    for _row, picked in prepared:
        if earliest is None or picked.after < earliest:
            earliest = picked.after
    events = (
        universe_data.split_events(day, earliest, sessions, read_actions, bucket, client)
        if prepared and earliest is not None
        else {}
    )
    floor = float(rules["minMarketCapUsd"])
    sized: list[dict[str, Any]] = []
    for row, picked in prepared:
        factor = share_count.split_factor(events.get(row["symbol"], []), picked.after, day)
        cap = picked.value * factor * float(row["close"])
        if cap < floor:
            continue
        carried = dict(row)
        carried["marketCap"] = cap
        carried["sharesSource"] = picked.source
        carried["sector"] = universe.sector_for(row["sic"], ranges, cik=str(row["cik"]), companies=company_sectors)
        sized.append(carried)
    members = [
        {
            "symbol": row["symbol"],
            "cik": row["cik"],
            "name": row["name"],
            "sic": None if row["sic"] is None else str(row["sic"]),
            "sector": row["sector"],
            "close": row["close"],
            "medianDollarVolume": row["medianDollarVolume"],
            "marketCap": row["marketCap"],
            "sharesSource": row["sharesSource"],
        }
        for row in sorted(sized, key=lambda item: item["symbol"])
    ]
    counts = {
        "assets": int(funnel.get("assets") or 0),
        "withCik": int(funnel.get("withCik") or 0),
        "price": int(funnel.get("price") or 0),
        "dollarVolume": int(funnel.get("dollarVolume") or 0),
        "fundamentals": stage["fundamentals"],
        "sic": stage["sic"],
        "annualReport": stage["annualReport"],
        "history": stage["history"],
        "marketCap": len(members),
    }
    sector_counts: dict[str, int] = {}
    share_sources: dict[str, int] = {}
    for row in members:
        sector_counts[row["sector"]] = sector_counts.get(row["sector"], 0) + 1
        share_sources[row["sharesSource"]] = share_sources.get(row["sharesSource"], 0) + 1
    universe_data.write_universe(
        day,
        members,
        counts,
        sector_counts,
        bucket,
        client,
        float(rules["maxMemberDropFraction"]),
        share_sources,
        price_as_of,
    )
    result = {
        "asOf": day.isoformat(),
        "status": "done",
        "members": len(members),
        "counts": counts,
        "sectors": sector_counts,
        "shareSources": share_sources,
        "symbols": [str(row["symbol"]) for row in members],
        "ciks": sorted({str(row["cik"]) for row in members}),
    }
    universe_data.write_build_progress(day, {"phase": "written", "result": result}, bucket, client)
    return result


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


def _liquid(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": str(row["symbol"]),
        "cik": str(row["cik"]),
        "name": str(row.get("name") or ""),
        "close": float(row["close"]),
        "medianDollarVolume": float(row["medianDollarVolume"]),
    }


def _write(
    day: date,
    companies: list[dict[str, Any]],
    ciks: list[str],
    phase: str,
    cursor: int,
    missing: list[str],
    counts: dict[str, int],
    prepared: list[tuple[dict[str, Any], share_count.Chosen]],
    funnel: dict[str, int],
    price_as_of: date | None,
    bucket: str,
    client: Any,
) -> None:
    universe_data.write_build_progress(
        day,
        {
            "ciks": ciks,
            "companies": [_liquid(row) for row in companies],
            "funnel": funnel,
            "priceAsOf": None if price_as_of is None else price_as_of.isoformat(),
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
    funnel: dict[str, int],
    price_as_of: date | None,
    bucket: str,
    client: Any,
) -> dict[str, Any] | None:
    """Missing files, without their bodies. ``None`` means every file is there."""
    cursor = int(saved.get("cursor") or 0) if saved.get("phase") == "exists" else 0
    missing = [str(cik) for cik in saved.get("missing") or []] if saved.get("phase") == "exists" else []

    def remember(at: int) -> None:
        _write(day, companies, ciks, "exists", at, missing, _blank(), [], funnel, price_as_of, bucket, client)

    for index, row in enumerate(companies):
        if index < cursor:
            continue
        if universe._out_of_time(context):
            remember(index)
            return _running(len(companies) - index)
        if not probe(str(row["cik"])):
            missing.append(str(row["cik"]))
        if (index + 1) % _BATCH == 0:
            remember(index + 1)
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
    probe: Probe | None,
    subs_of: Submissions,
    cover_of: Cover,
    bucket: str,
    client: Any,
    allow_refresh: bool,
    saved: dict[str, Any],
    ciks: list[str],
    funnel: dict[str, int],
    price_as_of: date | None,
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
        _write(day, companies, ciks, "qualify", at, missing, counts, prepared, funnel, price_as_of, bucket, client)

    for index, row in enumerate(companies):
        if index < cursor:
            continue
        if universe._out_of_time(context):
            remember(index)
            return _running(len(companies) - index)
        if missing and allow_refresh and probe is not None:
            if universe._out_of_time(context):
                remember(index)
                return _running(len(companies) - index)
            if not probe(str(row["cik"])):
                missing.append(str(row["cik"]))
            if (index + 1) % _BATCH == 0:
                remember(index + 1)
            continue
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
    remember(len(companies))
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
