"""The list of stocks the screen may consider.

Thresholds come from ``contracts/methodology.json`` and sectors from
``contracts/sic-sectors.json``. The four sector decisions are confirmed.
Other thresholds stay provisional. Bucket and table IO is in ``universe_data``.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import fundamentals_pit
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


def load_company_sectors(path: Path | None = None) -> dict[str, str]:
    """CIKs whose sector is not the sector of their SIC code."""
    raw = json.loads((path or _SECTORS).read_text(encoding="utf-8"))
    rows = raw.get("companySectors") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return {}
    return {
        _cik(row["cik"]): str(row["sector"])
        for row in rows
        if isinstance(row, dict) and str(row.get("cik") or "").strip() and row.get("sector")
    }


def sector_for(
    sic: object,
    ranges: list[dict[str, Any]] | None = None,
    *,
    cik: str | None = None,
    companies: dict[str, str] | None = None,
) -> str:
    """The sector for one SIC code. A listed CIK wins. An unmapped code is ``Other``."""
    if cik and str(cik).strip():
        table = companies if companies is not None else None if ranges is not None else load_company_sectors()
        found = table.get(_cik(cik)) if table else None
        if found:
            return found
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
            raise PriceSessionMissing("Raw prices are missing. Run backfill_prices first.")
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
            raise PriceSessionMissing(f"Raw prices missing for {day.isoformat()}. Run backfill_prices first.")
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
    company_sectors: dict[str, str] | None = None,
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
    if company_sectors is None and sectors is None:
        company_sectors = load_company_sectors()
    chosen_companies = company_sectors or {}
    listed = _screen_assets(assets, chosen)
    if not listed or not tickers or not sessions:
        return {"asOf": day.isoformat(), "status": "missing_inputs", "members": 0}
    joined = _joined(listed, tickers)
    needed = int(chosen["dollarVolumeWindowSessions"])
    window = _window(sessions, day, needed)
    import universe_screen

    done = universe_screen.published(day, name, client)
    if done is not None:
        return done
    saved = universe_screen.saved_liquid(day, name, client)
    if saved is None and joined and len(window) < needed:
        raise PriceWindowShort(day.isoformat())
    if saved is not None and _out_of_time(context):
        return {"asOf": day.isoformat(), "status": "running", "pending": len(saved["companies"])}
    if saved is None and joined and _out_of_time(context):
        return {"asOf": day.isoformat(), "status": "running", "pending": len(joined)}
    if saved is not None:
        companies = list(saved["companies"])
        funnel = dict(saved["funnel"])
        price_as_of = saved["priceAsOf"] if saved["priceAsOf"] is not None else (window[-1] if window else None)
    else:
        priced, liquid = _prices(joined, bars_of, window, chosen)
        companies = _one_listing(liquid)
        funnel = {
            "assets": len(listed),
            "withCik": len(joined),
            "price": len(_one_listing(priced)),
            "dollarVolume": len(companies),
        }
        price_as_of = window[-1] if window else None

    def screen(allow_refresh: bool) -> dict[str, Any]:
        return universe_screen.collect(
            companies,
            day,
            chosen,
            context,
            facts_of=facts_of,
            probe=None if read_facts is not None else universe_data.facts_present(name, client),
            subs_of=subs_of,
            cover_of=cover_of,
            bucket=name,
            client=client,
            allow_refresh=allow_refresh,
            funnel=funnel,
            price_as_of=price_as_of,
        )

    screened = screen(True)
    if screened["status"] == "refresh":
        outcome = refresh_of(list(screened["missing"]), context) or {}
        if not isinstance(outcome, dict) or outcome.get("status") != "done":
            status = str(outcome.get("status") or "running") if isinstance(outcome, dict) else "running"
            return {"asOf": day.isoformat(), "status": status, "pending": len(screened["missing"])}
        screened = screen(False)
    if screened["status"] != "ready":
        return {
            "asOf": day.isoformat(),
            "status": str(screened.get("status") or "running"),
            "pending": int(screened.get("pending") or 0),
        }
    if _out_of_time(context):
        return {"asOf": day.isoformat(), "status": "running", "pending": 0}
    return universe_screen.publish(
        list(screened["prepared"]),
        screened["counts"],
        funnel,
        day,
        chosen,
        sessions,
        read_actions,
        name,
        client,
        ranges,
        chosen_companies,
        price_as_of,
    )
