"""Replay the screen each month and chain a simple equal-weight portfolio."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Any

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
) -> list[dict[str, Any]]:
    """One factor row per month end, using only filings and prices public on that day."""
    rows: list[dict[str, Any]] = []
    for end in month_ends:
        body = snapshot_mod.build(symbol, "", end, pit_rows, adjusted, raw_close, shares, sessions)
        row: dict[str, Any] = {
            "symbol": symbol,
            "month": end[:7],
            "monthEnd": end,
            "sector": sector,
            "sic": sic,
            "close": raw_close,
            "medianDollarVolume": median_dollar_volume,
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
    for index, end in enumerate(month_ends[:-1]):
        nxt = month_ends[index + 1]
        if holdings_by_month is not None:
            chosen = list(holdings_by_month.get(end[:7]) or holdings_by_month.get(end) or [])
        else:
            ranked = sorted(screen.score(scores_by_month.get(end) or [], register), key=_rank_key)
            chosen = choose(ranked, size, cap)
        start_day = session_after(sessions, end, delay)
        end_day = session_after(sessions, nxt, delay)
        weights = {str(row["symbol"]): float(row["weight"]) for row in chosen}
        returns: list[float] = []
        for symbol in weights:
            value, used = name_return(prices.get(symbol) or [], start_day, end_day, rate)
            last_price_count += used
            if value is not None:
                returns.append(value)
        turned = 1.0 if not previous else one_way_turnover(previous, weights)
        spy_gross, _used = _gross(prices.get(spec["benchmark"]) or [], start_day, end_day)
        spy_net, _spy_used = name_return(prices.get(spec["benchmark"]) or [], start_day, end_day, rate)
        cash, _cash_used = _gross(prices.get(spec["cashProxy"]) or [], start_day, end_day)
        periods.append(
            {
                "month": end[:7],
                "strategy": period_return(returns, turned, cost) if returns else 0.0,
                "spyGross": spy_gross or 0.0,
                "spyNet": spy_net or 0.0,
                "cash": cash or 0.0,
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
        "metrics": _metrics(periods, curves, labels),
    }


def portfolio_size(value: object, register: dict[str, Any]) -> int | None:
    """The register size, or a sensitivity size from 10 to 40. Anything else is refused."""
    if value is None:
        return int(register["backtest"]["portfolioSize"])
    if isinstance(value, bool) or not isinstance(value, int) or not 10 <= value <= 40:
        return None
    return value


def run_id(register_hash: str, size: int, started_at: str) -> str:
    raw = f"{register_hash}:{size}:{started_at}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def run(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Chunked factor tables, then monthly portfolios, then one equity curve."""
    import store

    register = methodology.load()
    params = event.get("params") if isinstance(event.get("params"), dict) else {}
    size = portfolio_size(params.get("portfolioSize"), register)
    if size is None:
        return {"ok": False, "status": "failed", "error": "portfolioSize"}
    previous = store.get("JOB#backtest", "STATE") or {}
    saved = previous.get("params") if isinstance(previous.get("params"), dict) else {}
    if previous.get("status") in {"running", "paused", "failed"} and saved.get("runId"):
        identity = str(saved["runId"])
        started = str(saved.get("startedAt") or "")
    else:
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        identity = run_id(methodology.register_hash(register), size, started)
    import backtest_job

    ends = backtest_job.month_ends(register)
    part_ids = backtest_job.parts()
    if not ends or not part_ids:
        return {"ok": False, "status": "missing_inputs", "runId": identity}
    items: list[tuple[str, str]] = [("part", part) for part in part_ids]
    items.extend(("month", end) for end in ends)
    items.append(("equity", identity))
    import chunked

    result = chunked.run(
        "backtest",
        items,
        lambda item: backtest_job.perform(item, identity, size, register),
        context,
        params={"runId": identity, "portfolioSize": size, "startedAt": started},
    )
    return {"ok": True, "runId": identity, **result}


def _curves(periods: list[dict[str, Any]]) -> dict[str, list[float]]:
    curves = {name: [float(_START_VALUE)] for name in ("strategy", "spyGross", "spyNet", "cash")}
    for period in periods:
        for name in curves:
            curves[name].append(curves[name][-1] * (1 + float(period[name])))
    return curves


def _metrics(periods: list[dict[str, Any]], curves: dict[str, list[float]], labels: list[str]) -> dict[str, Any]:
    full = _window(periods, curves, labels, None, None)
    return {
        "full": full,
        "early": _window(periods, curves, labels, None, "2021-12"),
        "holdout": _window(periods, curves, labels, "2022-01", None),
        **full,
    }


def _window(
    periods: list[dict[str, Any]],
    curves: dict[str, list[float]],
    labels: list[str],
    start: str | None,
    end: str | None,
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
    strategy = [float(periods[index - 1]["strategy"]) for index in chosen]
    cash = [float(periods[index - 1]["cash"]) for index in chosen]
    spy = [float(periods[index - 1]["spyNet"]) for index in chosen]
    curve = curves["strategy"][first : last + 1]
    window_labels = [labels[first], *[labels[index] for index in chosen]]
    return {
        "cagr": backtest_metrics.cagr(curve),
        "volatility": backtest_metrics.annualised_volatility(strategy),
        "sharpe": backtest_metrics.sharpe(strategy, cash),
        "maxDrawdown": backtest_metrics.max_drawdown(curve, window_labels),
        "hitRate": backtest_metrics.hit_rate(strategy, spy),
        "worstWindow": backtest_metrics.worst_window(curve, window_labels),
        "averageTurnover": backtest_metrics.average_turnover(
            [float(periods[index - 1]["turnover"]) for index in chosen]
        ),
        "yearly": backtest_metrics.yearly_table(curve, curves["spyNet"][first : last + 1], window_labels),
    }


def _gross(series: list[dict[str, Any]], start: str | None, end: str | None) -> tuple[float | None, int]:
    value, used = name_return(series, start, end, 0)
    return value, used


def _rank_key(row: dict[str, Any]) -> tuple[int, str]:
    rank = row.get("rank")
    return (rank if isinstance(rank, int) else 10**9, str(row.get("symbol") or ""))


def _excluded(sic: object, ranges: list[list[int]]) -> bool:
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
        return False
    return any(low <= code <= high for low, high in ranges)


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
