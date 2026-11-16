"""Filings, trimmed company facts, and the point-in-time rows."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

import chunked
import config
import fundamentals_pit
import s3io
from alpaca_data import IngestDisabled

_INDEX_FORMS = frozenset({"10-K", "10-Q", "8-K", "10-K/A", "10-Q/A", "8-K/A"})
_REFRESH_FORMS = frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A"})
_CURSOR_PK = "JOB#ingest_filings"
_CURSOR_SK = "CURSOR"
STOCK_FRESH_DAYS = 450
Facts = Callable[[str], dict[str, Any]]
Index = Callable[[date], list[dict[str, str]]]


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


def _bucket(bucket: str | None) -> str:
    return bucket if bucket is not None else config.data_bucket_name()


def trim_facts(payload: dict[str, Any], maps: dict[str, dict[str, list[str]]] | None = None) -> dict[str, Any]:
    """Keep the mapped concepts. Names and unused tags are dropped."""
    chosen = maps if maps is not None else fundamentals_pit.load_tag_maps()
    facts = payload.get("facts") if isinstance(payload.get("facts"), dict) else {}
    kept: dict[str, dict[str, Any]] = {}
    for section in ("flows", "stocks", "shareFlows"):
        for tags in (chosen.get(section) or {}).values():
            for tag in tags:
                taxonomy = "dei" if tag.startswith("dei:") else "us-gaap"
                source = facts.get(taxonomy) or {}
                if not isinstance(source, dict):
                    continue
                concept = source.get(tag.removeprefix("dei:"))
                if isinstance(concept, dict):
                    kept.setdefault(taxonomy, {})[tag.removeprefix("dei:")] = concept
    return {"cik": payload.get("cik"), "facts": kept}


def _facts_key(cik: str) -> str:
    return f"fundamentals/raw/cik={cik}/companyfacts.json.gz"


def _pit_key(cik: str) -> str:
    return f"fundamentals/pit/cik={cik}/facts.jsonl.gz"


def _default_facts(cik: str) -> dict[str, Any]:
    import sec_edgar

    return sec_edgar.company_facts(cik)


def _default_index(day: date) -> list[dict[str, str]]:
    import sec_edgar

    return sec_edgar.daily_index(day)


def refresh(
    ciks: list[str],
    context: Any,
    *,
    job: str = "backfill_fundamentals",
    fetch_facts: Facts | None = None,
    bucket: str | None = None,
    client: Any = None,
    ingest_enabled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Trim each company file to the mapped tags and write the point-in-time rows."""
    _require(ingest_enabled)
    facts_of = fetch_facts or _default_facts
    name = _bucket(bucket)
    maps = fundamentals_pit.load_tag_maps()
    items = [_cik(cik) for cik in ciks]

    def process(cik: str) -> None:
        trimmed = trim_facts(_load_facts(facts_of, cik), maps)
        s3io.put_gzip_json(name, _facts_key(cik), trimmed, client=client)
        s3io.put_jsonl_gz(name, _pit_key(cik), fundamentals_pit.normalise(trimmed, maps), client=client)

    return chunked.run(job, items, process, context, params={"ciks": items})


def _load_facts(facts_of: Facts, cik: str) -> dict[str, Any]:
    import http_client

    try:
        return facts_of(cik)
    except http_client.HttpStatusError as exc:
        if exc.status != 404:
            raise
        return {"cik": cik, "facts": {}}


def _save_cursor(day: date) -> None:
    import store

    store.put({"pk": _CURSOR_PK, "sk": _CURSOR_SK, "lastDate": day.isoformat()})


def _cursor() -> date | None:
    import store

    item = store.get(_CURSOR_PK, _CURSOR_SK) or {}
    raw = item.get("lastDate")
    if not raw:
        return None
    return date.fromisoformat(str(raw)[:10])


def daily(
    ciks: list[str],
    on: date | datetime | str,
    context: Any,
    *,
    sessions: list[date] | None = None,
    fetch_index: Index | None = None,
    fetch_facts: Facts | None = None,
    bucket: str | None = None,
    client: Any = None,
    ingest_enabled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Write 10-K, 10-Q, and 8-K rows, then refresh the 10-K and 10-Q filers.

    ``sessions`` is the catch-up calendar. Only sessions after the stored
    cursor and on or before ``on`` are requested. An empty index before
    ``on`` is a day the SEC published nothing, so the cursor moves on.
    An empty index on ``on`` itself is not published yet.
    """
    _require(ingest_enabled)
    through = _as_date(on)
    if sessions is None:
        return _one_day(
            ciks,
            through,
            context,
            fetch_index=fetch_index,
            fetch_facts=fetch_facts,
            bucket=bucket,
            client=client,
            ingest_enabled=ingest_enabled,
        )
    cursor = _cursor()
    pending = [day for day in sessions if day <= through and (cursor is None or day > cursor)]
    filings = 0
    refreshed = 0
    status = "done"
    for day in pending:
        outcome = _one_day(
            ciks,
            day,
            context,
            fetch_index=fetch_index,
            fetch_facts=fetch_facts,
            bucket=bucket,
            client=client,
            ingest_enabled=ingest_enabled,
            empty="advance" if day < through else "wait",
        )
        if outcome["status"] != "done":
            return {"status": outcome["status"], "filings": filings, "refreshed": refreshed}
        filings += int(outcome["filings"])
        refreshed += int(outcome["refreshed"])
        status = "done"
    return {"status": status, "filings": filings, "refreshed": refreshed}


def _one_day(
    ciks: list[str],
    day: date,
    context: Any,
    *,
    fetch_index: Index | None,
    fetch_facts: Facts | None,
    bucket: str | None,
    client: Any,
    ingest_enabled: Callable[[], bool] | None,
    empty: str = "wait",
) -> dict[str, Any]:
    index_of = fetch_index or _default_index
    rows = list(index_of(day))
    if not rows:
        if empty == "advance":
            name = _bucket(bucket)
            s3io.put_jsonl_gz(name, f"filings/date={day.isoformat()}/index.jsonl.gz", [], client=client)
            _save_cursor(day)
            return {"status": "done", "filings": 0, "refreshed": 0}
        return {"status": "not_ready", "filings": 0, "refreshed": 0}
    universe = {_cik(cik) for cik in ciks}

    def _keep(row: dict[str, str]) -> bool:
        try:
            cik = _cik(row.get("cik"))
        except ValueError:
            return False
        return cik in universe and row.get("form") in _INDEX_FORMS

    kept = [row for row in rows if _keep(row)]
    name = _bucket(bucket)
    s3io.put_jsonl_gz(name, f"filings/date={day.isoformat()}/index.jsonl.gz", kept, client=client)
    refresh_ciks = sorted({_cik(row.get("cik")) for row in kept if row.get("form") in _REFRESH_FORMS})
    result: dict[str, Any] = {"status": "done", "cursor": 0, "total": 0}
    if refresh_ciks:
        result = refresh(
            refresh_ciks,
            context,
            job=f"ingest_filings_refresh#{day.isoformat()}",
            fetch_facts=fetch_facts,
            bucket=name,
            client=client,
            ingest_enabled=ingest_enabled,
        )
    if result.get("status") == "done":
        _save_cursor(day)
    return {"status": result.get("status"), "filings": len(kept), "refreshed": len(refresh_ciks)}


def coverage_report(
    ciks: list[str],
    on: date | datetime | str,
    *,
    bucket: str | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Share of companies with a value as of ``on``. Stored on the universe row."""
    day = _as_date(on)
    name = _bucket(bucket)
    maps = fundamentals_pit.load_tag_maps()
    flow_fields = list(maps["flows"])
    stock_fields = list(maps["stocks"])
    share_fields = list(maps.get("shareFlows") or {})
    counts = {field: 0 for field in flow_fields + stock_fields + share_fields}
    padded = [_cik(cik) for cik in ciks]
    for cik in padded:
        key = _pit_key(cik)
        if not s3io.exists(name, key, client=client):
            continue
        visible = fundamentals_pit.as_of(list(s3io.get_jsonl_gz(name, key, client=client)), day.isoformat())
        for field in flow_fields:
            if fundamentals_pit.ttm(visible, field) is not None:
                counts[field] += 1
        for field in stock_fields:
            if _fresh_stock(visible, field, day):
                counts[field] += 1
        for field in share_fields:
            if _fresh_share(visible, field, day):
                counts[field] += 1
    total = len(padded)
    flows = {field: (counts[field] / total if total else None) for field in flow_fields}
    stocks = {field: (counts[field] / total if total else None) for field in stock_fields}
    share_flows = {field: (counts[field] / total if total else None) for field in share_fields}
    report = _dynamo_ready(
        {"asOf": day.isoformat(), "companies": total, "flows": flows, "stocks": stocks, "shareFlows": share_flows}
    )
    import store

    pk = f"UNIVERSE#{day.isoformat()}"
    try:
        store.update_conditional(pk, "META", "SET coverage = :c", {":c": report}, "attribute_exists(pk)")
    except store.ConditionNotMet:
        pass
    return report


def _dynamo_ready(value: Any) -> Any:
    """DynamoDB stores a number as ``Decimal``. A float is rejected."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _dynamo_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_dynamo_ready(item) for item in value]
    return value


def _fresh_stock(rows: list[dict[str, Any]], field: str, day: date) -> bool:
    if fundamentals_pit.latest_stock(rows, field) is None:
        return False
    ends = [str(row["end"]) for row in rows if row.get("field") == field and row.get("end")]
    if not ends:
        return False
    return (day - date.fromisoformat(max(ends)[:10])).days <= STOCK_FRESH_DAYS


def _fresh_share(rows: list[dict[str, Any]], field: str, day: date) -> bool:
    ends = [str(row["end"]) for row in rows if row.get("field") == field and row.get("end")]
    if not ends:
        return False
    return (day - date.fromisoformat(max(ends)[:10])).days <= STOCK_FRESH_DAYS
