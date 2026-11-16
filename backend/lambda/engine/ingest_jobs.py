"""The ingest jobs tick and the dashboard can start.

A resumed price backfill keeps the ``start`` and ``end`` saved with the
job, so a new "yesterday" does not rebuild the month list. A universe
refresh saves the build date and runs the build again when the facts
are in.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
BACKFILL_START = "2016-01-01"
FILINGS_JOB_PREFIX = "ingest_filings_refresh#"
UNIVERSE_REFRESH_JOB = "universe_fundamentals_refresh"

Build = Callable[..., dict[str, Any]]
Refresh = Callable[..., dict[str, Any]]


def _yesterday(now: datetime | None) -> date:
    moment = now or datetime.now(NEW_YORK)
    return moment.astimezone(NEW_YORK).date() - timedelta(days=1)


def _params(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("params")
    return raw if isinstance(raw, dict) else {}


def _day(event: dict[str, Any], now: datetime | None) -> date:
    saved = _params(event).get("day")
    if saved:
        return date.fromisoformat(str(saved)[:10])
    return _yesterday(now)


def ingest_daily(
    event: dict[str, Any],
    context: Any,
    *,
    now: datetime | None = None,
    sessions: list[date] | None = None,
    symbols: list[str] | None = None,
    ciks: list[str] | None = None,
    raw: Callable[..., Any] | None = None,
    actions: Callable[..., Any] | None = None,
    filings: Callable[..., Any] | None = None,
    headlines: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """One New York session: prices, corporate actions, filings, and news."""
    day = _day(event, now)
    calendar = list(sessions or [])
    if day not in calendar:
        return {"ok": True, "status": "skipped_no_session", "asOf": day.isoformat()}
    names = list(symbols or [])
    companies = list(ciks or [])
    price = raw or _raw_day
    corporate = actions or _actions
    forms = filings or _filings
    stories = headlines or _news
    price(day, names)
    corporate(day - timedelta(days=7), day, calendar)
    forms(companies, day, context, sessions=calendar)
    stories(names, day)
    return {"ok": True, "status": "done", "asOf": day.isoformat()}


def weekly_refresh(
    event: dict[str, Any],
    context: Any,
    *,
    now: datetime | None = None,
    assets: list[dict[str, Any]] | None = None,
    tickers: dict[str, dict[str, Any]] | None = None,
    sessions: list[date] | None = None,
    build: Build | None = None,
    adjusted: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Refresh the lists, build the universe, then the adjusted prices."""
    day = _day(event, now)
    listed = list(assets or [])
    mapped = dict(tickers or {})
    calendar = list(sessions or [])
    screen = build or _universe
    outcome = screen(day, context, assets=listed, tickers=mapped, sessions=calendar)
    if not isinstance(outcome, dict) or outcome.get("status") != "done":
        status = outcome.get("status") if isinstance(outcome, dict) else "running"
        return {"ok": True, "status": status, "asOf": day.isoformat()}
    symbols = [str(row.get("symbol")) for row in listed if isinstance(row, dict) and row.get("symbol")]
    prices = adjusted or _adjusted
    refreshed = prices(symbols, BACKFILL_START, day, context)
    return {"ok": True, "status": refreshed.get("status", "done"), "asOf": day.isoformat(), "universe": outcome}


def backfill_prices(
    event: dict[str, Any],
    context: Any,
    *,
    now: datetime | None = None,
    sessions: list[date] | None = None,
    symbols: list[str] | None = None,
    run: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Raw bars from the saved window. A resume does not recompute the end date."""
    params = _params(event)
    start = str(params.get("start") or BACKFILL_START)
    end = str(params.get("end") or _yesterday(now).isoformat())
    names = list(params.get("symbols") or symbols or [])
    calendar = list(sessions or [])
    work = run or _price_backfill
    result = work(start, end, calendar, context, symbols=names)
    return {"ok": True, "start": start, "end": end, **result}


def backfill_fundamentals(
    event: dict[str, Any],
    context: Any,
    *,
    refresh: Refresh | None = None,
) -> dict[str, Any]:
    """Company facts for the saved CIKs, or the list on the event."""
    params = _params(event)
    ciks = list(params.get("ciks") or [])
    work = refresh or _facts
    result = work(ciks, context, job="backfill_fundamentals")
    return {"ok": True, **result}


def resume_filings(event: dict[str, Any], context: Any, *, refresh: Refresh | None = None) -> dict[str, Any]:
    """Continue one day's company-facts refresh. A finished row is removed by ``refresh``."""
    params = _params(event)
    work = refresh or _facts
    result = work(list(params.get("ciks") or []), context, job=str(event.get("job") or ""))
    return {"ok": True, **result}


def resume_universe(
    event: dict[str, Any], context: Any, *, refresh: Refresh | None = None, build: Build | None = None
) -> dict[str, Any]:
    """Finish the facts refresh, then build the universe for the saved date."""
    params = _params(event)
    work = refresh or _facts
    result = work(
        list(params.get("ciks") or []),
        context,
        job=UNIVERSE_REFRESH_JOB,
        as_of=str(params.get("asOf") or "") or None,
    )
    if result.get("status") != "done" or not params.get("asOf"):
        return {"ok": True, "refresh": result}
    screen = build or _universe
    built = screen(
        str(params["asOf"])[:10],
        context,
        assets=list(params.get("assets") or []),
        tickers=dict(params.get("tickers") or {}),
        sessions=list(params.get("sessions") or []),
    )
    return {"ok": True, "refresh": result, "build": built}


def _raw_day(day: date, symbols: list[str]) -> Any:
    import ingest_prices

    return ingest_prices.ingest_raw_day(day, symbols)


def _actions(start: date, end: date, sessions: list[date]) -> Any:
    import ingest_prices

    return ingest_prices.refresh_corporate_actions(start, end, sessions)


def _filings(ciks: list[str], day: date, context: Any, *, sessions: list[date]) -> Any:
    import ingest_fundamentals

    return ingest_fundamentals.daily(ciks, day, context, sessions=sessions)


def _news(symbols: list[str], day: date) -> Any:
    import ingest_news

    return ingest_news.daily(symbols, day)


def _universe(day: date | str, context: Any, **kwargs: Any) -> dict[str, Any]:
    import universe

    return universe.build(day, context, **kwargs)


def _adjusted(symbols: list[str], start: str, end: date, context: Any) -> dict[str, Any]:
    import ingest_prices

    return ingest_prices.refresh_adjusted(symbols, start, end, context)


def _price_backfill(start: str, end: str, sessions: list[date], context: Any, *, symbols: list[str]) -> dict[str, Any]:
    import ingest_prices

    return ingest_prices.backfill_raw(start, end, sessions, context, symbols=symbols)


def _facts(ciks: list[str], context: Any, *, job: str, as_of: str | None = None) -> dict[str, Any]:
    import ingest_fundamentals

    return ingest_fundamentals.refresh(ciks, context, job=job, as_of=as_of)
