"""The list of stocks the screen may consider.

Thresholds come from ``contracts/methodology.json``. Sectors come from
``contracts/sic-sectors.json``. Both are provisional until the owner
confirms them.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import fundamentals_pit
import s3io
from alpaca_data import IngestDisabled

_RULES = Path(__file__).resolve().parent / "contracts" / "methodology.json"
_SECTORS = Path(__file__).resolve().parent / "contracts" / "sic-sectors.json"
_ANNUAL = frozenset({"10-K", "10-K/A"})
Bars = Callable[[date], list[dict[str, Any]]]
Facts = Callable[[str], list[dict[str, Any]] | None]
Submissions = Callable[[str], dict[str, Any]]
Refresh = Callable[[list[str], Any], dict[str, Any]]


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
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
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


def _excluded(sic: object, ranges: list[list[int]]) -> bool:
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
        return False
    return any(int(low) <= code <= int(high) for low, high in ranges)


def _annual_ends(rows: list[dict[str, Any]], form: str) -> set[str]:
    forms = {form, f"{form}/A"}
    return {str(row["end"]) for row in rows if row.get("form") in forms and row.get("end")}


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


def _prices(
    rows: list[dict[str, Any]],
    read: Bars,
    window: list[date],
    rules: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split on the last close, then on median dollar volume."""
    if not window:
        return [], []
    last = window[-1]
    grouped: dict[str, list[tuple[date, float, float]]] = {}
    for day in window:
        for bar in read(day):
            if not isinstance(bar, dict):
                continue
            close = _number(bar.get("close"))
            volume = _number(bar.get("volume"))
            symbol = str(bar.get("symbol") or "")
            if close is None or volume is None or close <= 0 or volume < 0:
                continue
            grouped.setdefault(symbol, []).append((day, close, volume))
    priced: list[dict[str, Any]] = []
    liquid: list[dict[str, Any]] = []
    for row in rows:
        series = grouped.get(row["symbol"], [])
        close = next((price for day, price, _volume in series if day == last), None)
        if close is None or close < float(rules["minPriceUsd"]):
            continue
        carried = dict(row)
        carried["close"] = close
        priced.append(carried)
        median = _median([price * volume for _day, price, volume in series])
        if median < float(rules["minMedianDollarVolumeUsd"]):
            continue
        carried["medianDollarVolume"] = median
        liquid.append(carried)
    return priced, liquid


def _visible(rows: list[dict[str, Any]] | None, on: date) -> list[dict[str, Any]]:
    if not rows:
        return []
    return fundamentals_pit.as_of(rows, on.isoformat())


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
    bars_of = read_bars or _bars_reader(name, client)
    facts_of = read_facts or _facts_reader(name, client)
    subs_of = read_submissions or _default_submissions
    refresh_of = refresh or _refresh_reader(name, client)
    chosen = rules if rules is not None else load_rules()
    ranges = sectors if sectors is not None else load_sectors()
    listed = _screen_assets(assets, chosen)
    joined = _joined(listed, tickers)
    window = _window(sessions, day, int(chosen["dollarVolumeWindowSessions"]))
    priced, liquid = _prices(joined, bars_of, window, chosen)
    missing = sorted({row["cik"] for row in liquid if facts_of(row["cik"]) is None})
    if missing:
        refresh_of(missing, context)
    kept: list[dict[str, Any]] = []
    for row in liquid:
        visible = _visible(facts_of(row["cik"]), day)
        if not visible:
            continue
        carried = dict(row)
        carried["sic"] = subs_of(row["cik"]).get("sic")
        carried["rows"] = visible
        kept.append(carried)
    with_facts = kept
    allowed = [row for row in with_facts if not _excluded(row["sic"], chosen["excludeSicRanges"])]
    annual_form = str(chosen["requireAnnualReportForm"])
    reporting = [row for row in allowed if _annual_ends(row["rows"], annual_form)]
    seasoned = [
        row for row in reporting if len(_annual_ends(row["rows"], annual_form)) >= int(chosen["minFundamentalsYears"])
    ]
    sized: list[dict[str, Any]] = []
    floor = float(chosen["minMarketCapUsd"])
    for row in seasoned:
        shares = fundamentals_pit.latest_stock(row["rows"], "sharesOutstanding")
        if shares is None:
            continue
        cap = shares * float(row["close"])
        if cap < floor:
            continue
        carried = dict(row)
        carried["marketCap"] = cap
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
        }
        for row in sorted(sized, key=lambda item: item["symbol"])
    ]
    counts = {
        "assets": len(listed),
        "withCik": len(joined),
        "price": len(priced),
        "dollarVolume": len(liquid),
        "fundamentals": len(with_facts),
        "sic": len(allowed),
        "annualReport": len(reporting),
        "history": len(seasoned),
        "marketCap": len(members),
    }
    sector_counts: dict[str, int] = {}
    for row in members:
        sector_counts[row["sector"]] = sector_counts.get(row["sector"], 0) + 1
    _write(day, members, counts, sector_counts, name, client)
    return {"asOf": day.isoformat(), "members": len(members), "counts": counts, "sectors": sector_counts}


def _write(
    day: date,
    members: list[dict[str, Any]],
    counts: dict[str, int],
    sectors: dict[str, int],
    bucket: str | None,
    client: Any,
) -> None:
    import store

    s3io.put_jsonl_gz(bucket, f"universe/date={day.isoformat()}/members.jsonl.gz", members, client=client)
    pk = f"UNIVERSE#{day.isoformat()}"
    existing = store.get(pk, "META") or {}
    item: dict[str, Any] = {
        "pk": pk,
        "sk": "META",
        "gsi1pk": "UNIVERSE",
        "gsi1sk": day.isoformat(),
        "asOf": day.isoformat(),
        "members": len(members),
        "counts": counts,
        "sectors": sectors,
    }
    if "coverage" in existing:
        item["coverage"] = existing["coverage"]
    store.put(item)


def _bars_reader(bucket: str, client: Any) -> Bars:
    def read(day: date) -> list[dict[str, Any]]:
        key = f"prices/raw/date={day.isoformat()}/bars.jsonl.gz"
        if not s3io.exists(bucket, key, client=client):
            return []
        return list(s3io.get_jsonl_gz(bucket, key, client=client))

    return read


def _facts_reader(bucket: str, client: Any) -> Facts:
    def read(cik: str) -> list[dict[str, Any]] | None:
        key = f"fundamentals/pit/cik={cik}/facts.jsonl.gz"
        if not s3io.exists(bucket, key, client=client):
            return None
        return list(s3io.get_jsonl_gz(bucket, key, client=client))

    return read


def _default_submissions(cik: str) -> dict[str, Any]:
    import sec_edgar

    payload = sec_edgar.submissions(cik)
    return payload if isinstance(payload, dict) else {}


def _refresh_reader(bucket: str, client: Any) -> Refresh:
    def run(ciks: list[str], context: Any) -> dict[str, Any]:
        import ingest_fundamentals

        return ingest_fundamentals.refresh(ciks, context, bucket=bucket, client=client, ingest_enabled=lambda: True)

    return run
