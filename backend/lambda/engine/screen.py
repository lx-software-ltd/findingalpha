"""Score one date, keep the shortlist, and store it."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from typing import Any, Callable

import composite
import config
import methodology
import s3io
import snapshot as snapshot_mod

_OPS = {
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    "==": lambda left, right: left == right,
}
_SNAPSHOT_FIELDS = (
    "operatingIncome_ttm",
    "freeCashFlow_ttm",
    "longTermDebt",
    "shortTermDebt",
    "cash",
    "marketCap",
    "enterpriseValue",
)


def failed_filters(row: dict[str, Any], register: dict[str, Any]) -> list[str]:
    """The ids of the hard filters the row misses. A missing composite is its own failure."""
    if _number(row.get("composite")) is None:
        return ["composite"]
    return [str(rule["id"]) for rule in register["screen"]["hardFilters"] if not _rule(row, rule)]


def passes(row: dict[str, Any], register: dict[str, Any]) -> bool:
    """True when the row has a composite and meets every hard filter."""
    return not failed_filters(row, register)


def shortlist(rows: list[dict[str, Any]], register: dict[str, Any]) -> list[dict[str, Any]]:
    """The highest composites that pass, at most ``shortlistSize``, name as the tie break."""
    kept = [row for row in rows if passes(row, register)]
    kept.sort(key=lambda row: (-float(row["composite"]), str(row.get("symbol") or "")))
    return kept[: int(register["screen"]["shortlistSize"])]


def compute_factors(body: dict[str, Any], register: dict[str, Any]) -> dict[str, float | None]:
    """Every registered factor. A missing input or a bad denominator stays None."""
    values: dict[str, float | None] = {}
    for factor in register["factors"]:
        try:
            result = methodology.implementation(str(factor["implementation"]))(body, factor.get("parameters") or {})
        except (TypeError, ValueError, ZeroDivisionError, KeyError):
            result = None
        values[str(factor["id"])] = result if _number(result) is not None else None
    return values


def score(rows: list[dict[str, Any]], register: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach the composite, the failed filters, and a rank. A miss is unranked."""
    ids = [str(factor["id"]) for factor in register["factors"]]
    prepared = []
    for row in rows:
        item = dict(row)
        item["factors"] = {name: item.get(name) for name in ids}
        prepared.append(item)
    scored = composite.composite(prepared, register)
    ranked: list[dict[str, Any]] = []
    for row in scored:
        item = dict(row)
        item["failedFilters"] = failed_filters(item, register)
        item["rank"] = None
        ranked.append(item)
    survivors = [row for row in ranked if not row["failedFilters"]]
    survivors.sort(key=lambda row: (-float(row["composite"]), str(row.get("symbol") or "")))
    for index, row in enumerate(survivors, start=1):
        row["rank"] = index
    return ranked


def score_members(
    members: list[dict[str, Any]],
    register: dict[str, Any],
    snapshot_for: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    workers: int = 16,
) -> list[dict[str, Any]]:
    """Build one snapshot per member and score them together."""
    if workers <= 1 or len(members) <= 1:
        bodies = [snapshot_for(member) for member in members]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            bodies = list(pool.map(snapshot_for, members))
    rows = [_member_row(member, body, register) for member, body in zip(members, bodies, strict=True)]
    return score(rows, register)


def publish(
    day: str,
    rows: list[dict[str, Any]],
    register: dict[str, Any],
    *,
    bucket: str | None = None,
    client: Any = None,
    table: Any = None,
) -> None:
    """Write the full score file and one store row per shortlisted name."""
    import store

    name = bucket or config.data_bucket_name()
    ordered = sorted(rows, key=lambda row: str(row.get("symbol") or ""))
    s3io.put_jsonl_gz(name, f"screens/date={day}/scores.jsonl.gz", ordered, client=client)
    passed = sum(1 for row in rows if not row.get("failedFilters"))
    limit = int(register["screen"]["shortlistSize"])
    kept = [row for row in rows if isinstance(row.get("rank"), int) and int(row["rank"]) <= limit]
    saved = table or store
    pk = f"SCREEN#{day}"
    for old in saved.query_pk(pk, "RANK#"):
        saved.delete(pk, str(old["sk"]))
    saved.put(
        {
            "pk": pk,
            "sk": "META",
            "gsi1pk": "SCREENS",
            "gsi1sk": day,
            "asOf": day,
            "registerHash": methodology.register_hash(register),
            "shortlistSize": int(register["screen"]["shortlistSize"]),
            "counts": {"universe": len(rows), "passed": passed, "shortlisted": len(kept)},
        }
    )
    for row in kept:
        saved.put(_rank_item(pk, row))


def run(
    event: dict[str, Any],
    _context: Any = None,
    *,
    today: date | None = None,
    sessions: list[str] | None = None,
    members: list[dict[str, Any]] | None = None,
    snapshot_for: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    bucket: str | None = None,
    client: Any = None,
    table: Any = None,
) -> dict[str, Any]:
    """Score the newest universe on or before the date. The date defaults to the previous session."""
    register = methodology.load()
    day = _day(event, today=today, sessions=sessions, client=client)
    if day is None:
        return {"ok": False, "status": "missing_inputs"}
    listed = members if members is not None else _load_members(day, client)
    if not listed:
        return {"ok": False, "status": "missing_inputs", "asOf": day}
    reader = snapshot_for or (lambda member: _snapshot(member, day, client))
    scored = score_members(listed, register, reader)
    publish(day, scored, register, bucket=bucket, client=client, table=table)
    counts = {
        "universe": len(scored),
        "passed": sum(1 for row in scored if not row.get("failedFilters")),
        "shortlisted": sum(
            1
            for row in scored
            if isinstance(row.get("rank"), int) and int(row["rank"]) <= int(register["screen"]["shortlistSize"])
        ),
    }
    return {"ok": True, "status": "done", "asOf": day, "counts": counts}


def _member_row(member: dict[str, Any], body: dict[str, Any], register: dict[str, Any]) -> dict[str, Any]:
    row = {
        "symbol": str(member.get("symbol") or body.get("symbol") or ""),
        "name": str(member.get("name") or member.get("symbol") or ""),
        "sector": str(member.get("sector") or ""),
        "cik": str(member.get("cik") or ""),
    }
    for field in _SNAPSHOT_FIELDS:
        if field in body:
            row[field] = body[field]
    row.update(compute_factors(body, register))
    return row


def _rank_item(pk: str, row: dict[str, Any]) -> dict[str, Any]:
    rank = int(row["rank"])
    return _ready(
        {
            "pk": pk,
            "sk": f"RANK#{rank:04d}#{row.get('symbol')}",
            "rank": rank,
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "sector": row.get("sector"),
            "composite": row.get("composite"),
        }
    )


def _ready(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_ready(item) for item in value]
    return value


def _day(event: dict[str, Any], *, today: date | None, sessions: list[str] | None, client: Any) -> str | None:
    saved = (event.get("params") or {}).get("date") or event.get("date")
    if saved:
        return str(saved)[:10]
    calendar = sessions if sessions is not None else _calendar(client)
    if not calendar:
        return None
    moment = today or date.today()
    prior = [day for day in calendar if day < moment.isoformat()]
    return prior[-1] if prior else None


def _calendar(client: Any) -> list[str]:
    bucket = config.data_bucket_name()
    found: list[str] = []
    for key in s3io.list_keys(bucket, "reference/calendar/", client=client):
        payload = s3io.get_json(bucket, key, client=client)
        if isinstance(payload, dict):
            found.extend(str(day) for day in payload.get("sessions") or [])
    return sorted(set(found))


def _load_members(day: str, client: Any) -> list[dict[str, Any]]:
    bucket = config.data_bucket_name()
    dates = []
    for key in s3io.list_keys(bucket, "universe/date=", client=client):
        if "/members.jsonl.gz" not in key:
            continue
        stamp = key.split("date=", 1)[1][:10]
        if stamp <= day:
            dates.append(stamp)
    if not dates:
        return []
    latest = max(dates)
    return [
        row
        for row in s3io.get_jsonl_gz(bucket, f"universe/date={latest}/members.jsonl.gz", client=client)
        if isinstance(row, dict)
    ]


def _snapshot(member: dict[str, Any], day: str, client: Any) -> dict[str, Any]:
    bucket = config.data_bucket_name()
    cik = str(member.get("cik") or "")
    pit: list[dict[str, Any]] = []
    key = f"fundamentals/pit/cik={cik}/facts.jsonl.gz"
    if cik and s3io.exists(bucket, key, client=client):
        pit = [row for row in s3io.get_jsonl_gz(bucket, key, client=client) if isinstance(row, dict)]
    bars = _bars_for(str(member.get("symbol") or ""), client)
    close = _number(member.get("close"))
    cap = _number(member.get("marketCap"))
    shares = None if close in (None, 0) or cap is None else cap / close
    return snapshot_mod.build(
        str(member.get("symbol") or ""),
        cik,
        day,
        pit,
        bars,
        close,
        shares,
        _calendar(client) or None,
    )


def _bars_for(symbol: str, client: Any) -> list[dict[str, Any]]:
    bucket = config.data_bucket_name()
    found: list[dict[str, Any]] = []
    for key in s3io.list_keys(bucket, "prices/adj/", client=client):
        if not key.endswith("bars.jsonl.gz"):
            continue
        found.extend(
            row
            for row in s3io.get_jsonl_gz(bucket, key, client=client)
            if isinstance(row, dict) and str(row.get("symbol") or "") == symbol
        )
    return found


def _rule(row: dict[str, Any], rule: dict[str, Any]) -> bool:
    value = _number(row.get(rule["field"]))
    if value is None and rule.get("passWhenNetCash"):
        net = _net_debt(row)
        return net is not None and net <= 0
    if value is None:
        return False
    return bool(_OPS[str(rule["op"])](value, float(rule["value"])))


def _net_debt(row: dict[str, Any]) -> float | None:
    long_debt = _number(row.get("longTermDebt"))
    short_debt = _number(row.get("shortTermDebt"))
    cash = _number(row.get("cash"))
    if long_debt is None or short_debt is None or cash is None:
        return None
    return long_debt + short_debt - cash


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
