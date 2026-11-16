"""The ingest jobs tick and the dashboard can start.

The session is the New York trading day that has already closed. A run
at 12:00 in Hong Kong is 23:00 New York in winter and midnight in
summer, after the SEC daily index. A resumed price backfill keeps the
``start`` and ``end`` saved with the job. A universe build that stops
early is saved so tick can run it
again, and the adjusted refresh is a job tick can resume too.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
BACKFILL_START = "2016-01-01"
FILINGS_JOB_PREFIX = "ingest_filings_refresh#"
UNIVERSE_REFRESH_JOB = "universe_fundamentals_refresh"
UNIVERSE_BUILD_JOB = "universe_build"
ADJUSTED_JOB = "refresh_adjusted"
_CLOSE = time(16, 0)

Build = Callable[..., dict[str, Any]]
Refresh = Callable[..., dict[str, Any]]
Calendar = Callable[[date, date], list[date]]
Assets = Callable[[bool], list[dict[str, Any]]]
Tickers = Callable[[], dict[str, dict[str, Any]]]
Note = Callable[[date, str], None]
Coverage = Callable[[list[str], date], None]


def closed_session(now: datetime | None, calendar: list[date]) -> date | None:
    """The latest session whose 16:00 New York close is already in the past."""
    moment = (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)
    today = moment.date()
    after_close = moment.time() >= _CLOSE
    closed = [day for day in sorted(set(calendar)) if day < today or (day == today and after_close)]
    return closed[-1] if closed else None


def _params(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("params")
    if isinstance(raw, dict):
        return raw
    if not event.get("paramsInState"):
        return {}
    import store

    saved = (store.get(f"JOB#{event.get('job')}", "STATE") or {}).get("params")
    return saved if isinstance(saved, dict) else {}


def _moment(now: datetime | None) -> datetime:
    return (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)


def _dates(values: object) -> list[date]:
    if not isinstance(values, list):
        return []
    found: list[date] = []
    for value in values:
        if isinstance(value, datetime):
            found.append(value.date())
        elif isinstance(value, date):
            found.append(value)
        else:
            found.append(date.fromisoformat(str(value)[:10]))
    return found


def _calendar(sessions: list[date] | None, load: Calendar | None, start: date, end: date) -> list[date]:
    if sessions is not None:
        return list(sessions)
    return (load or _load_sessions)(start, end)


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
    news_symbols: list[str] | None = None,
    load_sessions: Calendar | None = None,
    load_assets: Assets | None = None,
    load_tickers: Tickers | None = None,
) -> dict[str, Any]:
    """One closed New York session: prices, corporate actions, filings, and news."""
    moment = _moment(now)
    calendar = _calendar(sessions, load_sessions, date(moment.year - 1, 1, 1), moment.date())
    saved = _params(event).get("day")
    day = date.fromisoformat(str(saved)[:10]) if saved else closed_session(now, calendar)
    if not calendar or day is None:
        status = "missing_inputs" if sessions is None and not calendar else "skipped_no_session"
        return {
            "ok": status == "skipped_no_session",
            "status": status,
            "asOf": None if day is None else day.isoformat(),
        }
    if day not in set(calendar):
        return {"ok": True, "status": "skipped_no_session", "asOf": day.isoformat()}
    listed = _assets(load_assets, False) if symbols is None or ciks is None else []
    names = list(symbols) if symbols is not None else _raw_symbols(listed, False)
    companies = list(ciks) if ciks is not None else _candidate_ciks(listed, (load_tickers or _load_tickers)())
    if not names or not companies:
        return {"ok": False, "status": "missing_inputs", "asOf": day.isoformat()}
    price = raw or _raw_day
    corporate = actions or _actions
    forms = filings or _filings
    stories = headlines or _news
    price(day, names)
    corporate(day - timedelta(days=7), day, calendar)
    filed = forms(companies, day, context, sessions=calendar)
    if isinstance(filed, dict) and filed.get("status") not in (None, "done"):
        return {"ok": True, "status": filed.get("status"), "asOf": day.isoformat()}
    stories(list(news_symbols or []), day)
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
    load_sessions: Calendar | None = None,
    load_assets: Assets | None = None,
    load_tickers: Tickers | None = None,
    note_build: Note | None = None,
    coverage: Coverage | None = None,
) -> dict[str, Any]:
    """Refresh the lists, build the universe, then the adjusted prices."""
    moment = _moment(now)
    calendar = _calendar(sessions, load_sessions, date(moment.year - 1, 1, 1), moment.date())
    saved = _params(event).get("day")
    day = date.fromisoformat(str(saved)[:10]) if saved else closed_session(now, calendar)
    listed = list(assets) if assets is not None else _assets(load_assets, False)
    mapped = dict(tickers) if tickers is not None else (load_tickers or _load_tickers)()
    if not calendar or not listed or not mapped or day is None or day not in set(calendar):
        status = "skipped_no_session" if calendar and day is not None and day not in set(calendar) else "missing_inputs"
        return {
            "ok": status == "skipped_no_session",
            "status": status,
            "asOf": None if day is None else day.isoformat(),
        }
    return _follow(day, context, listed, mapped, calendar, build, adjusted, note_build, coverage)


def backfill_prices(
    event: dict[str, Any],
    context: Any,
    *,
    now: datetime | None = None,
    sessions: list[date] | None = None,
    symbols: list[str] | None = None,
    assets: list[dict[str, Any]] | None = None,
    run: Callable[..., dict[str, Any]] | None = None,
    load_sessions: Calendar | None = None,
    load_assets: Assets | None = None,
) -> dict[str, Any]:
    """Raw bars from the saved window. A resume does not recompute the end date."""
    params = _params(event)
    moment = _moment(now)
    start = str(params.get("start") or BACKFILL_START)
    calendar = _calendar(sessions, load_sessions, date.fromisoformat(start[:10]), moment.date())
    end = str(params.get("end") or "")
    if not end:
        closed = closed_session(now, calendar)
        end = closed.isoformat() if closed else ""
    if params.get("symbols") or symbols is not None:
        names = list(params.get("symbols") or symbols or [])
        listed = list(assets) if assets is not None else None
    else:
        listed = list(assets) if assets is not None else _assets(load_assets, True)
        names = _raw_symbols(listed, True)
    if not names or not calendar or not end:
        return {"ok": False, "status": "missing_inputs", "start": start, "end": end}
    if run is None:
        result = _price_backfill(start, end, calendar, context, symbols=names, assets=listed or None)
    else:
        result = run(start, end, calendar, context, symbols=names)
    return {"ok": True, "start": start, "end": end, **result}


def backfill_fundamentals(
    event: dict[str, Any],
    context: Any,
    *,
    refresh: Refresh | None = None,
    load_assets: Assets | None = None,
    load_tickers: Tickers | None = None,
) -> dict[str, Any]:
    """Company facts for the saved CIKs, or every candidate when none were saved."""
    params = _params(event)
    ciks = list(params.get("ciks") or [])
    if not ciks:
        ciks = _candidate_ciks(_assets(load_assets, False), (load_tickers or _load_tickers)())
    if not ciks:
        return {"ok": False, "status": "missing_inputs"}
    result = (refresh or _facts)(ciks, context, job="backfill_fundamentals")
    return {"ok": True, **result}


def resume_filings(event: dict[str, Any], context: Any, *, refresh: Refresh | None = None) -> dict[str, Any]:
    """Continue one day's company-facts refresh. A finished row advances the filings cursor."""
    params = _params(event)
    result = (refresh or _facts)(list(params.get("ciks") or []), context, job=str(event.get("job") or ""))
    return {"ok": True, **result}


def resume_universe(
    event: dict[str, Any],
    context: Any,
    *,
    refresh: Refresh | None = None,
    build: Build | None = None,
    adjusted: Callable[..., dict[str, Any]] | None = None,
    load_sessions: Calendar | None = None,
    load_assets: Assets | None = None,
    load_tickers: Tickers | None = None,
    note_build: Note | None = None,
    coverage: Coverage | None = None,
) -> dict[str, Any]:
    """Finish the facts refresh, then build the universe for the saved date."""
    params = _params(event)
    result = (refresh or _facts)(
        list(params.get("ciks") or []),
        context,
        job=UNIVERSE_REFRESH_JOB,
        as_of=str(params.get("asOf") or "") or None,
    )
    if result.get("status") != "done" or not params.get("asOf"):
        return {"ok": True, "status": str(result.get("status") or "running"), "refresh": result}
    day = date.fromisoformat(str(params["asOf"])[:10])
    followed = _loaded_build(
        day, params, context, build, adjusted, load_sessions, load_assets, load_tickers, note_build, coverage
    )
    followed["refresh"] = result
    return followed


def resume_build(
    event: dict[str, Any],
    context: Any,
    *,
    build: Build | None = None,
    adjusted: Callable[..., dict[str, Any]] | None = None,
    load_sessions: Calendar | None = None,
    load_assets: Assets | None = None,
    load_tickers: Tickers | None = None,
    note_build: Note | None = None,
    coverage: Coverage | None = None,
) -> dict[str, Any]:
    """Continue a universe build that stopped before it finished."""
    params = _params(event)
    if not params.get("asOf"):
        return {"ok": False, "status": "missing_inputs"}
    day = date.fromisoformat(str(params["asOf"])[:10])
    return _loaded_build(
        day, params, context, build, adjusted, load_sessions, load_assets, load_tickers, note_build, coverage
    )


def resume_adjusted(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Continue the adjusted-price refresh from the symbols saved with it."""
    params = _params(event)
    symbols = [str(symbol) for symbol in params.get("symbols") or [] if str(symbol)]
    end = str(params.get("end") or "")
    if not end:
        return {"ok": False, "status": "missing_inputs"}
    result = _adjusted(symbols, str(params.get("start") or BACKFILL_START), date.fromisoformat(end[:10]), context)
    return {"ok": True, **result}


def _loaded_build(
    day: date,
    params: dict[str, Any],
    context: Any,
    build: Build | None,
    adjusted: Callable[..., dict[str, Any]] | None,
    load_sessions: Calendar | None,
    load_assets: Assets | None,
    load_tickers: Tickers | None,
    note_build: Note | None,
    coverage: Coverage | None,
) -> dict[str, Any]:
    listed = list(params["assets"]) if "assets" in params else _assets(load_assets, False)
    mapped = dict(params["tickers"]) if "tickers" in params else (load_tickers or _load_tickers)()
    calendar = (
        _dates(params["sessions"])
        if "sessions" in params
        else (load_sessions or _load_sessions)(date(day.year - 1, 1, 1), day)
    )
    if not listed or not mapped or not calendar:
        (note_build or _note_build)(day, "failed")
        return {"ok": False, "status": "missing_inputs", "asOf": day.isoformat()}
    return _follow(day, context, listed, mapped, calendar, build, adjusted, note_build, coverage)


def _follow(
    day: date,
    context: Any,
    listed: list[dict[str, Any]],
    mapped: dict[str, dict[str, Any]],
    calendar: list[date],
    build: Build | None,
    adjusted: Callable[..., dict[str, Any]] | None,
    note_build: Note | None,
    coverage: Coverage | None,
) -> dict[str, Any]:
    outcome = (build or _universe)(day, context, assets=listed, tickers=mapped, sessions=calendar)
    status = str(outcome.get("status") or "running") if isinstance(outcome, dict) else "running"
    body: dict[str, Any] = {"ok": status != "failed", "status": status, "asOf": day.isoformat(), "build": outcome}
    if status != "done":
        if not (status == "running" and _facts_open()):
            (note_build or _note_build)(day, "running" if status == "running" else "failed")
        return body
    (note_build or _note_build)(day, "done")
    import monthly_stats

    symbols = monthly_stats.for_adjusted([str(symbol) for symbol in (outcome.get("symbols") or [])], mapped)
    if adjusted is None:
        _save_adjusted(symbols, day, hold=True)
    (coverage or _coverage)([str(cik) for cik in (outcome.get("ciks") or [])], day)
    if adjusted is None:
        _save_adjusted(symbols, day, hold=False)
    refreshed = (adjusted or _adjusted)(symbols, BACKFILL_START, day, context)
    body["status"] = refreshed.get("status", "done")
    return body


def _assets(load: Assets | None, include_inactive: bool) -> list[dict[str, Any]]:
    return (load or _load_assets)(include_inactive)


def _candidate_ciks(assets: list[dict[str, Any]], tickers: dict[str, dict[str, Any]]) -> list[str]:
    import universe

    joined = universe._joined(universe._screen_assets(assets, universe.load_rules()), tickers)
    return sorted({str(row["cik"]) for row in joined})


def _raw_symbols(assets: list[dict[str, Any]], include_inactive: bool) -> list[str]:
    import ingest_prices

    return ingest_prices.raw_symbols(assets, include_inactive=include_inactive)


def _note_build(day: date, status: str) -> None:
    import store
    import timeutil

    kept = status if status in {"running", "paused", "failed", "done"} else "failed"
    store.put(
        {
            "pk": f"JOB#{UNIVERSE_BUILD_JOB}",
            "sk": "STATE",
            "status": kept,
            "cursor": 0 if kept == "running" else 1,
            "total": 1,
            "gsi1pk": "JOBSTATE",
            "gsi1sk": UNIVERSE_BUILD_JOB,
            "params": {"asOf": day.isoformat()},
            "updatedAt": timeutil.format_iso_millis(timeutil.utc_now()),
        }
    )


def _facts_open() -> bool:
    """The facts refresh is the job tick should resume, not a second build."""
    import store

    item = store.get(f"JOB#{UNIVERSE_REFRESH_JOB}", "STATE") or {}
    return item.get("status") in {"running", "paused"}


def _save_adjusted(symbols: list[str], day: date, *, hold: bool) -> None:
    """Save the adjusted refresh before the coverage report.

    The lease keeps tick from starting a second copy. An empty list is kept
    because the refresh still writes SPY and BIL.
    """
    import chunked
    import store
    import timeutil

    now = timeutil.utc_now()
    item: dict[str, Any] = {
        "pk": f"JOB#{ADJUSTED_JOB}",
        "sk": "STATE",
        "status": "running",
        "cursor": 0,
        "total": 1,
        "gsi1pk": "JOBSTATE",
        "gsi1sk": ADJUSTED_JOB,
        "params": {"symbols": list(symbols), "start": BACKFILL_START, "end": day.isoformat()},
        "updatedAt": timeutil.format_iso_millis(now),
    }
    if hold:
        item["leaseUntil"] = timeutil.format_iso_millis(now + chunked.LEASE)
    store.put(item)


def _coverage(ciks: list[str], day: date) -> None:
    import ingest_fundamentals

    if ciks:
        ingest_fundamentals.coverage_report(ciks, day)


def _load_sessions(start: date, end: date) -> list[date]:
    import market_calendar

    return market_calendar.sessions(start, end, market_calendar.fetch_alpaca_year)


def _load_assets(include_inactive: bool) -> list[dict[str, Any]]:
    import alpaca_data

    found = list(alpaca_data.list_assets("active"))
    if include_inactive:
        found.extend(alpaca_data.list_assets("inactive"))
    return found


def _load_tickers() -> dict[str, dict[str, Any]]:
    import sec_edgar

    return sec_edgar.ticker_map()


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


def _price_backfill(
    start: str,
    end: str,
    sessions: list[date],
    context: Any,
    *,
    symbols: list[str],
    assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    import ingest_prices

    return ingest_prices.backfill_raw(start, end, sessions, context, symbols=symbols, assets=assets)


def _facts(ciks: list[str], context: Any, *, job: str, as_of: str | None = None) -> dict[str, Any]:
    import ingest_fundamentals

    return ingest_fundamentals.refresh(ciks, context, job=job, as_of=as_of)
