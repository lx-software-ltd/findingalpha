"""The list of stocks the screen may consider.

Thresholds come from ``contracts/methodology.json``. Sectors come from
``contracts/sic-sectors.json``. Both are provisional until the owner
confirms them. Bucket and table IO lives in ``universe_data``.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import fundamentals_pit
import share_count
import universe_data
from alpaca_data import IngestDisabled

_RULES = Path(__file__).resolve().parent / "contracts" / "methodology.json"
_SECTORS = Path(__file__).resolve().parent / "contracts" / "sic-sectors.json"
Bars = Callable[[date], list[dict[str, Any]] | None]
Facts = Callable[[str], list[dict[str, Any]] | None]
Submissions = Callable[[str], dict[str, Any]]
Refresh = Callable[[list[str], Any], dict[str, Any]]
Actions = Callable[[date], list[dict[str, Any]]]
Cover = Callable[[str, date], dict[str, Any] | None]


class PriceSessionMissing(RuntimeError):
    """A session in the window has no price file, so nothing is written."""


_STOP_WITH_MS_LEFT = 120_000


class PriceWindowShort(RuntimeError):
    """The session list is shorter than the dollar-volume window."""


def _require(check: Callable[[], bool] | None) -> None:
    allowed = check if check is not None else _default_ingest
    if not allowed():
        raise IngestDisabled()


def _default_ingest() -> bool:
    import kill_switch

    return kill_switch.is_enabled("ingestEnabled")


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _cik(value: object) -> str:
    text = str(value).strip()
    if not text.isdigit():
        raise ValueError("cik must be digits")
    return text.zfill(10)


def load_rules(path: Path | None = None) -> dict[str, Any]:
    """The universe section. Missing keys are a contract error."""
    raw = json.loads((path or _RULES).read_text(encoding="utf-8"))
    section = raw.get("universe")
    if not isinstance(section, dict):
        raise ValueError("methodology contract is missing universe")
    required = (
        "exchanges",
        "requireMarginable",
        "requireAnnualReportForm",
        "excludeSicRanges",
        "minPriceUsd",
        "minMedianDollarVolumeUsd",
        "dollarVolumeWindowSessions",
        "minMarketCapUsd",
        "minFundamentalsYears",
        "maxAnnualReportAgeDays",
        "maxMemberDropFraction",
    )
    missing = [name for name in required if name not in section]
    if missing:
        raise ValueError(f"universe rules missing {', '.join(missing)}")
    return section


def load_sectors(path: Path | None = None) -> list[dict[str, Any]]:
    """SIC ranges in order. A code in none of them is ``Other``."""
    raw = json.loads((path or _SECTORS).read_text(encoding="utf-8"))
    ranges = raw.get("ranges") if isinstance(raw, dict) else None
    if not isinstance(ranges, list) or not ranges:
        raise ValueError("sic sector contract is missing ranges")
    return ranges


def sector_for(sic: object, ranges: list[dict[str, Any]] | None = None) -> str:
    """The sector for one SIC code. An unmapped code is ``Other``."""
    chosen = ranges if ranges is not None else load_sectors()
    code = _sic_code(sic)
    if code is None:
        return "Other"
    for row in chosen:
        if int(row["from"]) <= code <= int(row["to"]):
            return str(row["sector"])
    return "Other"


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _window(days: list[date], on: date, count: int) -> list[date]:
    chosen = sorted(day for day in days if day <= on)
    if count < 1:
        return []
    return chosen[-count:]


def _sic_code(sic: object) -> int | None:
    try:
        text = str(sic).strip()
        if not text:
            return None
        return int(text)
    except (TypeError, ValueError):
        return None


def _excluded(sic: object, ranges: list[list[int]]) -> bool:
    code = _sic_code(sic)
    if code is None:
        return True
    return any(int(low) <= code <= int(high) for low, high in ranges)


def _full_year(row: dict[str, Any]) -> bool:
    if row.get("kind") != "flow":
        return False
    try:
        start = date.fromisoformat(str(row.get("start"))[:10])
        end = date.fromisoformat(str(row.get("end"))[:10])
    except (TypeError, ValueError):
        return False
    return fundamentals_pit.period_class(start, end) == "year"


def _annual_filings(rows: list[dict[str, Any]], form: str) -> dict[str, str]:
    """Map each 10-K filing date to that filing's latest full fiscal year.

    Comparative columns share the filing date, so only the latest year
    in the filing counts. An amendment is its own filing of the same year.
    """
    forms = {form, f"{form}/A"}
    found: dict[str, str] = {}
    for row in rows:
        if row.get("form") not in forms or not _full_year(row):
            continue
        filed = str(row.get("filed") or "")[:10]
        end = str(row.get("end") or "")[:10]
        if not filed or not end:
            continue
        current = found.get(filed)
        if current is None or end > current:
            found[filed] = end
    return found


def _recent_annual(rows: list[dict[str, Any]], form: str, on: date, max_age: int) -> bool:
    filings = _annual_filings(rows, form)
    if not filings:
        return False
    latest = date.fromisoformat(max(filings))
    return (on - latest).days <= max_age


def _screen_assets(assets: list[dict[str, Any]], rules: dict[str, Any]) -> list[dict[str, Any]]:
    exchanges = set(rules["exchanges"])
    kept: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        symbol = str(asset.get("symbol") or "").strip()
        if not symbol or asset.get("exchange") not in exchanges or asset.get("status") != "active":
            continue
        if asset.get("tradable") is not True:
            continue
        if rules["requireMarginable"] and asset.get("marginable") is not True:
            continue
        kept.append(asset)
    return kept


def _joined(assets: list[dict[str, Any]], tickers: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for asset in assets:
        symbol = str(asset.get("symbol") or "").strip()
        entry = tickers.get(symbol)
        if not isinstance(entry, dict) or not str(entry.get("cik") or "").strip():
            continue
        rows.append(
            {
                "symbol": symbol,
                "cik": _cik(entry["cik"]),
                "name": str(entry.get("name") or asset.get("name") or ""),
            }
        )
    return rows


def _prefer(row: dict[str, Any], current: dict[str, Any]) -> bool:
    volume = float(row["medianDollarVolume"])
    other = float(current["medianDollarVolume"])
    if volume != other:
        return volume > other
    return str(row["symbol"]) < str(current["symbol"])


def _one_listing(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per CIK: the listing with the higher median dollar volume."""
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        current = best.get(row["cik"])
        if current is None or _prefer(row, current):
            best[row["cik"]] = row
    return [best[key] for key in sorted(best)]


def _prices(
    rows: list[dict[str, Any]],
    read: Bars,
    window: list[date],
    rules: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split on the last close, then on a full-window median dollar volume."""
    if not window:
        if rows:
            raise PriceSessionMissing("no sessions")
        return [], []
    needed = int(rules["dollarVolumeWindowSessions"])
    grouped: dict[str, list[tuple[date, float, float]]] = {}
    last = window[-1]

    def consume(day: date, bars: list[dict[str, Any]]) -> None:
        for bar in bars:
            if not isinstance(bar, dict):
                continue
            close = _number(bar.get("close"))
            volume = _number(bar.get("volume"))
            symbol = str(bar.get("symbol") or "")
            if close is None or volume is None or close <= 0 or volume < 0:
                continue
            grouped.setdefault(symbol, []).append((day, close, volume))

    for day in window:
        bars = read(day)
        if rows and (bars is None or (day == last and not bars)):
            raise PriceSessionMissing(day.isoformat())
        consume(day, list(bars or []))
    priced: list[dict[str, Any]] = []
    liquid: list[dict[str, Any]] = []
    floor = float(rules["minMedianDollarVolumeUsd"])
    for row in rows:
        series = grouped.get(row["symbol"], [])
        close = next((price for day, price, _volume in series if day == last), None)
        if close is None or close < float(rules["minPriceUsd"]):
            continue
        carried = dict(row)
        carried["close"] = close
        carried["medianDollarVolume"] = _median([price * volume for _day, price, volume in series])
        priced.append(carried)
        if len(series) < needed or carried["medianDollarVolume"] < floor:
            continue
        liquid.append(carried)
    return priced, liquid


def _visible(rows: list[dict[str, Any]] | None, on: date) -> list[dict[str, Any]]:
    if not rows:
        return []
    return fundamentals_pit.as_of(rows, on.isoformat())


def _remaining(context: Any) -> int | None:
    method = getattr(context, "get_remaining_time_in_millis", None)
    if method is None:
        return None
    try:
        return int(method())
    except (TypeError, ValueError):
        return None


def _out_of_time(context: Any) -> bool:
    left = _remaining(context)
    return left is not None and left < _STOP_WITH_MS_LEFT


def build(
    on: date | datetime | str,
    context: Any,
    *,
    assets: list[dict[str, Any]],
    tickers: dict[str, dict[str, Any]],
    sessions: list[date],
    read_bars: Bars | None = None,
    read_facts: Facts | None = None,
    read_submissions: Submissions | None = None,
    refresh: Refresh | None = None,
    read_actions: Actions | None = None,
    read_cover: Cover | None = None,
    bucket: str | None = None,
    client: Any = None,
    ingest_enabled: Callable[[], bool] | None = None,
    rules: dict[str, Any] | None = None,
    sectors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply each rule, then write the members and the universe row."""
    _require(ingest_enabled)
    day = _as_date(on)
    import config

    name = bucket if bucket is not None else config.data_bucket_name()
    bars_of = read_bars or universe_data.bars_reader(name, client)
    facts_of = read_facts or universe_data.facts_reader(name, client)
    subs_of = read_submissions or universe_data.submissions_reader(name, client)
    refresh_of = refresh or universe_data.refresh_runner(name, client, day)
    cover_of = read_cover or universe_data.cover_reader(name, client)
    chosen = rules if rules is not None else load_rules()
    ranges = sectors if sectors is not None else load_sectors()
    listed = _screen_assets(assets, chosen)
    if not listed or not tickers or not sessions:
        return {"asOf": day.isoformat(), "status": "missing_inputs", "members": 0}
    joined = _joined(listed, tickers)
    needed = int(chosen["dollarVolumeWindowSessions"])
    window = _window(sessions, day, needed)
    if joined and len(window) < needed:
        raise PriceWindowShort(day.isoformat())
    priced, liquid = _prices(joined, bars_of, window, chosen)
    priced_companies = _one_listing(priced)
    companies = _one_listing(liquid)
    loaded: dict[str, list[dict[str, Any]] | None] = {}

    def facts_once(cik: str) -> list[dict[str, Any]] | None:
        if cik not in loaded:
            loaded[cik] = facts_of(cik)
        return loaded[cik]

    missing = sorted({row["cik"] for row in companies if facts_once(row["cik"]) is None})
    if missing:
        outcome = refresh_of(missing, context) or {}
        if not isinstance(outcome, dict) or outcome.get("status") != "done":
            status = str(outcome.get("status") or "running") if isinstance(outcome, dict) else "running"
            return {"asOf": day.isoformat(), "status": status, "pending": len(missing)}
        for cik in missing:
            loaded.pop(cik, None)
    kept: list[dict[str, Any]] = []
    for index, row in enumerate(companies):
        visible = _visible(facts_once(row["cik"]), day)
        if not visible:
            continue
        if _out_of_time(context):
            return {"asOf": day.isoformat(), "status": "running", "pending": len(companies) - index}
        carried = dict(row)
        carried["sic"] = subs_of(row["cik"]).get("sic")
        carried["rows"] = visible
        kept.append(carried)
    annual_form = str(chosen["requireAnnualReportForm"])
    allowed = [row for row in kept if not _excluded(row["sic"], chosen["excludeSicRanges"])]
    max_age = int(chosen["maxAnnualReportAgeDays"])
    reporting = [row for row in allowed if _recent_annual(row["rows"], annual_form, day, max_age)]
    seasoned = [
        row
        for row in reporting
        if len(set(_annual_filings(row["rows"], annual_form).values())) >= int(chosen["minFundamentalsYears"])
    ]
    prepared: list[tuple[dict[str, Any], share_count.Chosen]] = []
    earliest: date | None = None
    for index, row in enumerate(seasoned):
        picked = share_count.choose(row["rows"], day)
        if picked is None:
            if _out_of_time(context):
                return {"asOf": day.isoformat(), "status": "running", "pending": len(seasoned) - index}
            picked = share_count.from_cover(cover_of(row["cik"], day), day)
        if picked is None:
            continue
        prepared.append((row, picked))
        if earliest is None or picked.after < earliest:
            earliest = picked.after
    events = (
        universe_data.split_events(day, earliest, sessions, read_actions, name, client)
        if prepared and earliest is not None
        else {}
    )
    floor = float(chosen["minMarketCapUsd"])
    sized: list[dict[str, Any]] = []
    for row, picked in prepared:
        factor = share_count.split_factor(events.get(row["symbol"], []), picked.after, day)
        cap = picked.value * factor * float(row["close"])
        if cap < floor:
            continue
        carried = dict(row)
        carried["marketCap"] = cap
        carried["sharesSource"] = picked.source
        carried["sector"] = sector_for(row["sic"], ranges)
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
        "assets": len(listed),
        "withCik": len(joined),
        "price": len(priced_companies),
        "dollarVolume": len(companies),
        "fundamentals": len(kept),
        "sic": len(allowed),
        "annualReport": len(reporting),
        "history": len(seasoned),
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
        name,
        client,
        float(chosen["maxMemberDropFraction"]),
        share_sources,
        window[-1] if window else None,
    )
    return {
        "asOf": day.isoformat(),
        "status": "done",
        "members": len(members),
        "counts": counts,
        "sectors": sector_counts,
        "shareSources": share_sources,
    }
