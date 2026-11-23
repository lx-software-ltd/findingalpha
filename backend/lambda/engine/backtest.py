"""Replay the screen each month and chain a simple equal-weight portfolio."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Any, Callable

import backtest_metrics
import fundamentals_pit
import methodology
import screen
import snapshot as snapshot_mod

_START_VALUE = 100


def holding_return(adj_start: float, adj_end: float, split_start: float, split_end: float, rate: float) -> float:
    """Price return plus the dividend return after withholding."""
    total = adj_end / adj_start - 1
    price = split_end / split_start - 1
    return price + (1 - rate) * (total - price)


def one_way_turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    """Half the sum of absolute weight changes. A full replacement is 1."""
    symbols = set(previous) | set(current)
    return 0.5 * sum(abs(current.get(symbol, 0) - previous.get(symbol, 0)) for symbol in symbols)


def period_return(name_returns: list[float], turnover: float, cost_bps: float) -> float:
    """Equal-weight mean, minus a round trip on the share that changed."""
    return sum(name_returns) / len(name_returns) - turnover * 2 * cost_bps / 10000


def choose(ranked: list[dict[str, Any]], size: int, max_per_sector: int) -> list[dict[str, Any]]:
    """Walk the ranking. Skip a name once its sector is full, and stop at ``size``."""
    chosen: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for row in ranked:
        if not isinstance(row.get("rank"), int):
            continue
        sector = str(row.get("sector") or "")
        if counts.get(sector, 0) >= max_per_sector:
            continue
        chosen.append(row)
        counts[sector] = counts.get(sector, 0) + 1
        if len(chosen) >= size:
            break
    weight = 1 / len(chosen) if chosen else 0
    return [{**row, "weight": weight} for row in chosen]


def eligible(row: dict[str, Any], rules: dict[str, Any]) -> bool:
    """Price, dollar volume, market cap, history, and the SIC exclusion."""
    close = _number(row.get("close"))
    volume = _number(row.get("medianDollarVolume"))
    cap = _number(row.get("marketCap"))
    years = row.get("historyYears")
    if close is None or close < float(rules["minPriceUsd"]):
        return False
    if volume is None or volume < float(rules["minMedianDollarVolumeUsd"]):
        return False
    if cap is None or cap < float(rules["minMarketCapUsd"]):
        return False
    if isinstance(years, bool) or not isinstance(years, (int, float)) or years < float(rules["minFundamentalsYears"]):
        return False
    return not _excluded(row.get("sic"), rules.get("excludeSicRanges") or [])


def complete_month_ends(ends: list[str], sessions: list[str]) -> list[str]:
    """Month ends that are the last stored session of their calendar month."""
    last: dict[str, str] = {}
    for day in sorted(sessions):
        if len(day) >= 7:
            last[day[:7]] = day
    return [end for end in ends if last.get(end[:7]) == end]


def session_after(sessions: list[str], day: str, delay: int) -> str | None:
    """The session ``delay`` steps after ``day``. A delay of 1 is the next session."""
    later = [item for item in sessions if item > day]
    if delay <= 0:
        return day if day in sessions else (later[0] if later else None)
    if len(later) < delay:
        return None
    return later[delay - 1]


def name_return(
    series: list[dict[str, Any]], start: str | None, end: str | None, rate: float
) -> tuple[float | None, int]:
    """Net return between two sessions. A missing end price uses the last price and counts 1."""
    if start is None or end is None:
        return None, 0
    start_bar = next((bar for bar in series if bar.get("date") == start), None)
    end_bar = next((bar for bar in series if bar.get("date") == end), None)
    used = 0
    if end_bar is None:
        earlier = [bar for bar in series if str(bar.get("date")) <= end]
        end_bar = earlier[-1] if earlier else None
        if end_bar is None or str(end_bar.get("date")) < start:
            return None, 0
        used = 1
    if start_bar is None:
        return None, used
    value = holding_return(
        float(start_bar["adj"]),
        float(end_bar["adj"]),
        float(start_bar["split"]),
        float(end_bar["split"]),
        rate,
    )
    return value, used


def rows_for_symbol(
    symbol: str,
    month_ends: list[str],
    pit_rows: list[dict[str, Any]],
    adjusted: list[dict[str, Any]],
    raw_close: float | None,
    shares: float | None,
    sessions: list[str] | None,
    register: dict[str, Any],
    *,
    sector: str = "",
    sic: object = None,
    median_dollar_volume: float | None = None,
    by_month: dict[str, dict[str, Any]] | None = None,
    shares_on: Callable[[str], float | None] | None = None,
) -> list[dict[str, Any]]:
    """One factor row per month end, using only filings and prices public on that day.

    ``by_month`` supplies that month's close and dollar volume. Without it,
    the single ``raw_close`` is used for every month, which the tests do.
    """
    rows: list[dict[str, Any]] = []
    for end in month_ends:
        if by_month is None:
            close: float | None = raw_close
            volume = median_dollar_volume
        else:
            stats = by_month.get(end[:7]) or {}
            close = _number(stats.get("close"))
            volume = _number(stats.get("medianDollarVolume"))
        share_count = shares_on(end) if shares_on is not None else shares
        body = snapshot_mod.build(symbol, "", end, pit_rows, adjusted, close, share_count, sessions)
        row: dict[str, Any] = {
            "symbol": symbol,
            "month": end[:7],
            "monthEnd": end,
            "sector": sector,
            "sic": sic,
            "close": close,
            "medianDollarVolume": volume,
            "marketCap": body.get("marketCap"),
            "historyYears": history_years(pit_rows, end),
        }
        for field in ("operatingIncome_ttm", "freeCashFlow_ttm", "longTermDebt", "shortTermDebt", "cash"):
            row[field] = body.get(field)
        row.update(screen.compute_factors(body, register))
        rows.append(row)
    return rows


def history_years(pit_rows: list[dict[str, Any]], on: str) -> int:
    """Distinct annual statements that were public on ``on``."""
    years: set[str] = set()
    for row in fundamentals_pit.as_of(pit_rows, on):
        start = _as_date(row.get("start"))
        end = _as_date(row.get("end"))
        if row.get("kind") == "flow" and start and end and fundamentals_pit.period_class(start, end) == "year":
            years.add(end.isoformat())
    return len(years)


def replay(
    month_ends: list[str],
    scores_by_month: dict[str, list[dict[str, Any]]],
    prices: dict[str, list[dict[str, Any]]],
    sessions: list[str],
    register: dict[str, Any],
    *,
    portfolio_size: int | None = None,
    holdings_by_month: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Hold each month's portfolio from the delayed close until the next one."""
    spec = register["backtest"]
    size = int(portfolio_size or spec["portfolioSize"])
    delay = int(spec["tradeDelaySessions"])
    cost = float(spec["costBpsPerSide"])
    rate = float(spec["dividendWithholdingRate"])
    cap = int(spec["maxNamesPerSector"])
    previous: dict[str, float] = {}
    periods: list[dict[str, Any]] = []
    last_price_count = 0
    unpriced = 0
    missing_benchmark = 0
    latest = _latest_bar(prices)
    for index, end in enumerate(month_ends[:-1]):
        nxt = month_ends[index + 1]
        start_day = session_after(sessions, end, delay)
        end_day = session_after(sessions, nxt, delay)
        if start_day is None or end_day is None or (latest and end_day > latest):
            break
        if holdings_by_month is not None:
            chosen = list(holdings_by_month.get(end[:7]) or holdings_by_month.get(end) or [])
        else:
            ranked = sorted(screen.score(scores_by_month.get(end) or [], register), key=_rank_key)
            chosen = choose(ranked, size, cap)
        weights = {str(row["symbol"]): float(row["weight"]) for row in chosen}
        cash, _cash_used = _gross(prices.get(spec["cashProxy"]) or [], start_day, end_day)
        spy_gross, _used = _gross(prices.get(spec["benchmark"]) or [], start_day, end_day)
        spy_net, _spy_used = name_return(prices.get(spec["benchmark"]) or [], start_day, end_day, rate)
        if cash is None or spy_gross is None or spy_net is None:
            missing_benchmark += 1
        returns: list[float] = []
        for symbol in weights:
            value, used = name_return(prices.get(symbol) or [], start_day, end_day, rate)
            last_price_count += used
            if value is None:
                unpriced += 1
                if cash is not None:
                    returns.append(cash)
                continue
            returns.append(value)
        if not weights:
            turned = 0.0
            strategy: float | None = cash
        else:
            turned = 1.0 if not previous else one_way_turnover(previous, weights)
            strategy = period_return(returns, turned, cost) if returns else cash
        periods.append(
            {
                "month": nxt[:7],
                "months": month_span(end, nxt),
                "strategy": strategy,
                "spyGross": spy_gross,
                "spyNet": spy_net,
                "cash": cash,
                "turnover": turned,
                "holdings": [str(row["symbol"]) for row in chosen],
            }
        )
        previous = weights
    curves = _curves(periods)
    labels = ["start", *[period["month"] for period in periods]]
    return {
        "periods": periods,
        "labels": labels,
        "curves": curves,
        "lastPriceCount": last_price_count,
        "unpricedCount": unpriced,
        "missingBenchmarkCount": missing_benchmark,
        "metrics": _metrics(periods, curves, labels, cost),
    }


def continued_run(previous: dict[str, Any], size: int) -> tuple[str, str] | None:
    """The saved run when it is the same size and has not failed three times.

    A different size, a finished run, and a terminal failure start a new id
    so later months are not mixed with holdings already written.
    """
    if previous.get("status") not in {"running", "paused", "failed"}:
        return None
    saved = raw if isinstance(raw := previous.get("params"), dict) else {}
    if isinstance(saved.get("portfolioSize"), bool) or not saved.get("runId"):
        return None
    try:
        saved_size = int(saved["portfolioSize"])
        failures = int(previous.get("failures") or 0)
    except (TypeError, ValueError, KeyError):
        return None
    if saved_size != size or (previous.get("status") == "failed" and failures >= 3):
        return None
    return str(saved["runId"]), str(saved.get("startedAt") or "")


def size_conflict(previous: dict[str, Any], size: int) -> str | None:
    status = str(previous.get("status") or "")
    if status not in {"running", "paused", "failed"}:
        return None
    try:
        if status == "failed" and int(previous.get("failures") or 0) >= 3:
            return None
    except (TypeError, ValueError):
        return "unfinished backtest"
    raw = (previous.get("params") or {}).get("portfolioSize") if isinstance(previous.get("params"), dict) else None
    from decimal import Decimal

    if isinstance(raw, Decimal) and raw.is_finite() and raw == raw.to_integral_value():
        raw = int(raw)
    if type(raw) is int:
        return None if raw == size else f"unfinished backtest is {raw} names"
    return None if status == "failed" else "unfinished backtest"


def portfolio_size(value: object, register: dict[str, Any]) -> int | None:
    """The register size, or a sensitivity size inside the register bounds."""
    bounds = register["backtest"]
    if value is None:
        return int(bounds["portfolioSize"])
    low, high = int(bounds["portfolioSizeMin"]), int(bounds["portfolioSizeMax"])
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return None
    return value


def run_id(register_hash: str, size: int, started_at: str) -> str:
    raw = f"{register_hash}:{size}:{started_at}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def run(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Chunked factor tables, then monthly portfolios, then one equity curve."""
    import store

    register = methodology.load()
    params = raw if isinstance(raw := event.get("params"), dict) else {}
    size = portfolio_size(params.get("portfolioSize"), register)
    if size is None:
        return {"ok": False, "status": "failed", "error": "portfolioSize"}
    previous = store.get("JOB#backtest", "STATE") or {}
    conflict = size_conflict(previous, size)
    if conflict:
        return {"ok": False, "status": "failed", "error": conflict}
    continued = continued_run(previous, size)
    if continued is not None:
        identity, started = continued
    else:
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        identity = run_id(methodology.register_hash(register), size, started)
    import backtest_inputs
    import backtest_job

    ends = backtest_job.month_ends(register)
    part_ids = backtest_job.parts()
    if not ends or not part_ids:
        return {"ok": False, "status": "missing_inputs", "runId": identity}
    items: list[tuple[str, str]] = [("actions", year) for year in backtest_inputs.action_years(ends)]
    items.append(("inputs", "snapshot"))
    items.extend(("part", part) for part in part_ids)
    items.extend(("month", end) for end in ends)
    items.extend(("marks", part) for part in part_ids)
    items.append(("equity", identity))
    import chunked

    result = chunked.run(
        "backtest",
        items,
        lambda item: backtest_job.perform(item, identity, size, register),
        context,
        params={"runId": identity, "portfolioSize": size, "startedAt": started},
        enabled=_ingest_enabled,
    )
    return {"ok": True, "runId": identity, **result}


def _ingest_enabled() -> bool:
    import kill_switch

    return kill_switch.is_enabled("ingestEnabled")


def _curves(periods: list[dict[str, Any]]) -> dict[str, list[float]]:
    curves = {name: [float(_START_VALUE)] for name in ("strategy", "spyGross", "spyNet", "cash")}
    for period in periods:
        for name in curves:
            curves[name].append(curves[name][-1] * (1 + _or_zero(period.get(name))))
    return curves


def _metrics(
    periods: list[dict[str, Any]], curves: dict[str, list[float]], labels: list[str], cost: float
) -> dict[str, Any]:
    full = _window(periods, curves, labels, None, None, cost)
    return {
        "full": full,
        "early": _window(periods, curves, labels, None, "2021-12", cost),
        "holdout": _window(periods, curves, labels, "2022-01", None, cost),
        **full,
    }


def _window(
    periods: list[dict[str, Any]],
    curves: dict[str, list[float]],
    labels: list[str],
    start: str | None,
    end: str | None,
    cost: float,
) -> dict[str, Any]:
    chosen = [
        index
        for index, label in enumerate(labels)
        if index and (start is None or label >= start) and (end is None or label <= end)
    ]
    if not chosen:
        return {}
    first = chosen[0] - 1
    last = chosen[-1]
    strategy = [_or_zero(periods[index - 1].get("strategy")) for index in chosen]
    cash = [_or_zero(periods[index - 1].get("cash")) for index in chosen]
    spanned = sum(int(periods[index - 1].get("months") or 1) for index in chosen)
    spy = [_or_zero(periods[index - 1].get("spyNet")) for index in chosen]
    gross = [_or_zero(periods[index - 1].get("spyGross")) for index in chosen]
    turnovers = [float(periods[index - 1]["turnover"]) for index in chosen]
    curve = curves["strategy"][first : last + 1]
    spy_curve = curves["spyNet"][first : last + 1]
    gross_curve = curves["spyGross"][first : last + 1]
    window_labels = [labels[first], *[labels[index] for index in chosen]]
    return {
        "cagr": backtest_metrics.cagr(curve, spanned),
        "volatility": backtest_metrics.annualised_volatility(strategy),
        "sharpe": backtest_metrics.sharpe(strategy, cash),
        "maxDrawdown": backtest_metrics.max_drawdown(curve, window_labels),
        "hitRate": backtest_metrics.hit_rate(strategy, spy),
        "worstWindow": backtest_metrics.worst_window(curve, window_labels),
        "averageTurnover": backtest_metrics.average_turnover(turnovers),
        "costDrag": backtest_metrics.yearly_cost_drag(turnovers, cost),
        "longestBehind": backtest_metrics.longest_behind(curve, spy_curve, window_labels),
        "benchmarks": {
            "spyNet": _series(spy_curve, spy, cash, window_labels, spanned),
            "spyGross": _series(gross_curve, gross, cash, window_labels, spanned),
        },
        "yearly": backtest_metrics.yearly_table(curve, spy_curve, window_labels),
    }


def month_span(start: str, end: str) -> int:
    """Calendar months from ``start`` to ``end``. A same-month pair counts as one."""
    if len(start) < 7 or len(end) < 7:
        return 1
    span = (int(end[:4]) - int(start[:4])) * 12 + (int(end[5:7]) - int(start[5:7]))
    return span if span > 0 else 1


def _series(
    curve: list[float], returns: list[float], cash: list[float], labels: list[str], months: int
) -> dict[str, Any]:
    return {
        "cagr": backtest_metrics.cagr(curve, months),
        "volatility": backtest_metrics.annualised_volatility(returns),
        "sharpe": backtest_metrics.sharpe(returns, cash),
        "maxDrawdown": backtest_metrics.max_drawdown(curve, labels),
    }


def _latest_bar(prices: dict[str, list[dict[str, Any]]]) -> str:
    latest = ""
    for series in prices.values():
        for bar in series:
            day = str(bar.get("date") or "")
            if day > latest:
                latest = day
    return latest


def _or_zero(value: object) -> float:
    number = _number(value)
    return 0.0 if number is None else number


def _gross(series: list[dict[str, Any]], start: str | None, end: str | None) -> tuple[float | None, int]:
    value, used = name_return(series, start, end, 0)
    return value, used


def _rank_key(row: dict[str, Any]) -> tuple[int, str]:
    rank = row.get("rank")
    return (rank if isinstance(rank, int) else 10**9, str(row.get("symbol") or ""))


def _excluded(sic: object, ranges: list[list[int]]) -> bool:
    """A missing or unreadable SIC is excluded, matching the live universe."""
    try:
        text = str(sic).strip()
        if not text:
            return True
        code = int(text)
    except (TypeError, ValueError):
        return True
    return any(int(low) <= code <= int(high) for low, high in ranges)


def _as_date(value: object) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
