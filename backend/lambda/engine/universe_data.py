"""Bucket and table IO for one universe build.

The screen lives in ``universe``. This module caches industry codes,
reads splits, and writes the member list without replacing coverage.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Callable

import s3io

REFRESH_JOB = "universe_fundamentals_refresh"
_ACTION_PREFIX = "corporate-actions/date="
_ACTION_SUFFIX = "/actions.jsonl.gz"


class UniverseShrink(RuntimeError):
    """The new list is far smaller than the last finished build, so nothing was written."""

    def __init__(self, previous: int, members: int) -> None:
        super().__init__(f"universe shrank from {previous} to {members}")
        self.previous = previous
        self.members = members


def bars_reader(bucket: str, client: Any) -> Callable[[date], list[dict[str, Any]] | None]:
    """Bars for one session. ``None`` means the price file is not there."""

    def read(day: date) -> list[dict[str, Any]] | None:
        key = f"prices/raw/date={day.isoformat()}/bars.jsonl.gz"
        if not s3io.exists(bucket, key, client=client):
            return None
        return list(s3io.get_jsonl_gz(bucket, key, client=client))

    return read


def facts_reader(bucket: str, client: Any) -> Callable[[str], list[dict[str, Any]] | None]:
    def read(cik: str) -> list[dict[str, Any]] | None:
        key = f"fundamentals/pit/cik={cik}/facts.jsonl.gz"
        if not s3io.exists(bucket, key, client=client):
            return None
        return list(s3io.get_jsonl_gz(bucket, key, client=client))

    return read


def submissions_reader(bucket: str, client: Any) -> Callable[[str], dict[str, Any]]:
    """SIC for one CIK. A stored code is reused so the next build skips the SEC."""

    def read(cik: str) -> dict[str, Any]:
        key = f"reference/sic/cik={cik}.json"
        if s3io.exists(bucket, key, client=client):
            found = s3io.get_json(bucket, key, client=client)
            if isinstance(found, dict) and str(found.get("sic") or "").strip():
                return {"sic": str(found["sic"]).strip()}
        import sec_edgar

        payload = sec_edgar.submissions(cik)
        sic = payload.get("sic") if isinstance(payload, dict) else None
        text = "" if sic is None else str(sic).strip()
        if text:
            s3io.put_json(bucket, key, {"sic": text}, client=client)
        return {"sic": text or None}

    return read


_COVER_FORMS = frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A"})


def cover_reader(bucket: str, client: Any) -> Callable[[str, date], dict[str, Any] | None]:
    """Class totals from the latest 10-K or 10-Q cover. One filing is parsed once."""

    def read(cik: str, on: date) -> dict[str, Any] | None:
        import sec_edgar
        import share_count

        payload = sec_edgar.submissions(cik)
        filing = _latest_filing(payload, on)
        if filing is None:
            return None
        filed, accession, document = filing
        key = f"reference/shares/cik={cik}.json"
        if s3io.exists(bucket, key, client=client):
            cached = s3io.get_json(bucket, key, client=client)
            if isinstance(cached, dict) and str(cached.get("accession") or "") == accession:
                return cached
        parsed = share_count.parse_cover_shares(sec_edgar.filing(cik, accession, document)) or {}
        stored = {
            "filed": filed,
            "accession": accession,
            "end": parsed.get("end"),
            "value": parsed.get("value"),
            "source": "coverClasses",
        }
        s3io.put_json(bucket, key, stored, client=client)
        return stored

    return read


def _latest_filing(payload: dict[str, Any], on: date) -> tuple[str, str, str] | None:
    filings = payload.get("filings") if isinstance(payload, dict) else None
    recent = filings.get("recent") if isinstance(filings, dict) else None
    if not isinstance(recent, dict):
        return None
    best: tuple[str, str, str] | None = None
    limit = on.isoformat()
    rows = zip(
        recent.get("form") or [],
        recent.get("filingDate") or [],
        recent.get("accessionNumber") or [],
        recent.get("primaryDocument") or [],
        strict=False,
    )
    for form, filed, accession, document in rows:
        day = str(filed)[:10]
        if str(form) not in _COVER_FORMS or not day or day > limit or not accession or not document:
            continue
        if best is None or day > best[0]:
            best = (day, str(accession), str(document))
    return best


def refresh_runner(bucket: str, client: Any, on: date | None = None) -> Callable[[list[str], Any], dict[str, Any]]:
    """Refresh missing facts under this build's own job, not the backfill."""

    def run(ciks: list[str], context: Any) -> dict[str, Any]:
        import ingest_fundamentals

        return ingest_fundamentals.refresh(
            ciks,
            context,
            job=REFRESH_JOB,
            bucket=bucket,
            client=client,
            ingest_enabled=lambda: True,
            as_of=None if on is None else on.isoformat(),
        )

    return run


def split_events(
    on: date,
    earliest: date,
    sessions: list[date],
    read: Callable[[date], list[dict[str, Any]]] | None,
    bucket: str,
    client: Any,
) -> dict[str, list[tuple[date, float]]]:
    """Split ratios by symbol. Injected readers see ``sessions``; the bucket sees stored files."""
    if read is None:
        days = _stored_action_days(bucket, client, earliest, on)
        reader = _actions_reader(bucket, client)
    else:
        days = [day for day in sessions if earliest < day <= on]
        reader = read
    found: dict[str, list[tuple[date, float]]] = {}
    for day in days:
        for row in reader(day) or []:
            if not isinstance(row, dict):
                continue
            ratio = _split_ratio(row)
            symbol = str(row.get("symbol") or "")
            if ratio is None or not symbol:
                continue
            ex = _day(row.get("exDate"), day)
            found.setdefault(symbol, []).append((ex, ratio))
    return found


def write_universe(
    day: date,
    members: list[dict[str, Any]],
    counts: dict[str, int],
    sectors: dict[str, int],
    bucket: str,
    client: Any,
    drop_fraction: float,
    share_sources: dict[str, int] | None = None,
) -> None:
    """Write members, then set this build's fields. Coverage on the row is not replaced."""
    _refuse_shrink(day, len(members), drop_fraction)
    s3io.put_jsonl_gz(bucket, f"universe/date={day.isoformat()}/members.jsonl.gz", members, client=client)
    import store

    store.update(
        f"UNIVERSE#{day.isoformat()}",
        "META",
        "SET #gsi1pk = :gsi1pk, #gsi1sk = :gsi1sk, #asOf = :asOf, #members = :members, "
        "#counts = :counts, #sectors = :sectors, #shareSources = :shareSources",
        {
            ":gsi1pk": "UNIVERSE",
            ":gsi1sk": day.isoformat(),
            ":asOf": day.isoformat(),
            ":members": len(members),
            ":counts": counts,
            ":sectors": sectors,
            ":shareSources": share_sources or {},
        },
        {
            "#gsi1pk": "gsi1pk",
            "#gsi1sk": "gsi1sk",
            "#asOf": "asOf",
            "#members": "members",
            "#counts": "counts",
            "#sectors": "sectors",
            "#shareSources": "shareSources",
        },
    )


def _refuse_shrink(day: date, members: int, fraction: float) -> None:
    previous = _previous_members(day)
    if previous is None or previous <= 0:
        return
    if members < previous * (1 - float(fraction)):
        raise UniverseShrink(previous, members)


def _previous_members(day: date) -> int | None:
    import store

    current = store.get(f"UNIVERSE#{day.isoformat()}", "META") or {}
    if _finished(current):
        return _whole(current.get("members"))
    prior = [
        row for row in store.query_gsi1("UNIVERSE") if str(row.get("gsi1sk") or "") < day.isoformat() and _finished(row)
    ]
    if not prior:
        return None
    latest = max(prior, key=lambda row: str(row["gsi1sk"]))
    return _whole(latest.get("members"))


def _finished(row: dict[str, Any]) -> bool:
    return isinstance(row.get("counts"), dict) and _whole(row.get("members")) is not None


def _whole(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    return int(value)


def _stored_action_days(bucket: str, client: Any, earliest: date, on: date) -> list[date]:
    days: list[date] = []
    for key in s3io.list_keys(bucket, "corporate-actions/", client=client):
        if not key.startswith(_ACTION_PREFIX) or not key.endswith(_ACTION_SUFFIX):
            continue
        token = key[len(_ACTION_PREFIX) : -len(_ACTION_SUFFIX)]
        try:
            day = date.fromisoformat(token)
        except ValueError:
            continue
        if earliest < day <= on:
            days.append(day)
    return days


def _actions_reader(bucket: str, client: Any) -> Callable[[date], list[dict[str, Any]]]:
    def read(day: date) -> list[dict[str, Any]]:
        key = f"{_ACTION_PREFIX}{day.isoformat()}{_ACTION_SUFFIX}"
        if not s3io.exists(bucket, key, client=client):
            return []
        return list(s3io.get_jsonl_gz(bucket, key, client=client))

    return read


def _split_ratio(row: dict[str, Any]) -> float | None:
    if str(row.get("type") or "") not in {"forward_split", "reverse_split"}:
        return None
    old = _number(row.get("splitFrom"))
    new = _number(row.get("splitTo"))
    if old is None or new is None or old <= 0 or new <= 0:
        return None
    return new / old


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _day(value: object, fallback: date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return fallback
