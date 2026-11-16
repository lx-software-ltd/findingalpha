# Plan: M06 screen and backtest

**Status**: In progress. The screen, the monthly table, the backtest, the metrics, and the page are in. The three live runs and the memo wait until the price history is current and the fundamentals files exist. No result has been invented.
**Zone**: yellow. Red parts: the `backtest` section of the register, new
routes in CDK.

## Goal

1. A **screen** job that scores the whole universe on a given date with
   the M05 factors and stores a ranked shortlist of about 60 names.
2. A **backtest** that replays the same screen every month from 2017 to
   today using only data that was public at each date, and reports
   whether a simple portfolio built from it beat the S&P 500 after
   costs and dividend withholding tax.
3. A research memo the owner reads before any model or broker work
   starts.

## Non-goals

- The backtest does **not** test the model committee. A language model
  already knows what happened after 2017, so replaying it would be
  cheating. Only the numeric screen is tested.
- No leverage in this backtest. M09 replays the leverage rule on top of
  the equity curve produced here.
- No parameter search. See "Honesty rules".
- No orders, no broker.

## Honesty rules

A backtest is easy to fool yourself with. These are not optional.

1. **Fix the settings first.** The register from M05 is used as it is.
   Do not change a weight, a threshold or the factor list after seeing
   a result.
2. **If a setting must change**, write in the memo what changed, why,
   and both results, before and after.
3. **Holdout.** Report 2017 to 2021 and 2022 to today separately. The
   second period is the holdout. Nothing is ever chosen by looking at
   it.
4. **Report the bad news.** Worst year, worst drawdown, longest stretch
   behind the benchmark, turnover and costs go in the memo with the
   same prominence as the return.
5. **If the screen does not beat SPY net of tax and costs, stop and
   tell the owner.** Do not adjust until it passes. A failed backtest
   is a result, and it changes the plan.
6. **Name the biases** that remain (section below).

## Files

```
contracts/methodology.json                  (add "backtest" section; red)
backend/lambda/engine/screen.py             test_screen.py
backend/lambda/engine/backtest.py           test_backtest.py
backend/lambda/engine/backtest_metrics.py   test_backtest_metrics.py
backend/lambda/engine/jobs_handler.py       (jobs screen, backtest)
backend/lambda/engine/api_handler.py        (routes)
backend/infrastructure/lib/api-routes.ts    (red)
apps/admin_web/src/components/ui/LineChart.tsx  (+ test)
apps/admin_web/src/pages/ScreenPage.tsx     (+ nav, mock, test)
docs/research/backtest-2017-2026.md
```

`screen.passes` and `screen.shortlist` already apply the M05 hard
filters, including `passWhenNetCash` when the debt ratio is missing.
This milestone adds the job, the stored shortlist, and the backtest.

## Invariants this change preserves

- The screen and the backtest call the same `snapshot`, `factors_*` and
  `composite` code. There is no second implementation.
- Point in time everywhere: a value filed or a price dated after the
  simulated date is never read.
- Results carry the register hash.
- Standard library only.

## Register addition

```json
"backtest": {
  "status": "provisional",
  "firstScreenMonth": "2017-02",
  "portfolioSize": 20,
  "weighting": "equal",
  "maxNamesPerSector": 5,
  "tradeDelaySessions": 1,
  "costBpsPerSide": 10,
  "dividendWithholdingRate": 0.30,
  "benchmark": "SPY",
  "cashProxy": "BIL"
}
```

`firstScreenMonth` is 2017-02 because momentum needs 252 sessions of
prices and the data starts in 2016.

## Steps

### M06-T01 Screen

`screen.run(date)`:

1. Load the newest universe file dated on or before `date`.
2. For each member, in a thread pool of 16: read the point-in-time
   rows and the adjusted bars, build the snapshot as of `date`, compute
   every factor.
3. `composite.composite(rows, register)`.
4. Apply the hard filters from `register.screen.hardFilters`. Record
   for each company which filter failed.
5. Sort the survivors by composite, highest first. Ties break by
   symbol so the order is deterministic.
6. Write `screens/date=<date>/scores.jsonl.gz` with every member
   (factors, z-scores, group scores, composite, failed filters, rank or
   `null`). Write the `SCREEN#<date>` `META` row (counts, register
   hash) and one `RANK#` row per shortlisted name.

Job `screen` with optional `date` (default: previous session). Manual
run allowed. Checks `ingestEnabled`.

Tests: a fixture universe of 30 invented companies; the shortlist is
the top N of those that pass; a company failing a filter is not
ranked; a `None` composite is not ranked; equal composites sort by
symbol; rerunning writes identical output.

### M06-T02 Monthly statistics table

The universe rules need each symbol's price and liquidity at every
historical month end. Reading 2,700 daily files per backtest is slow,
so build a table once.

Job `backfill_monthly_stats` (chunked, one month per item): for each
month from 2016-03, read that month's last 60 raw daily files and
write `prices/monthly/month=<yyyy-mm>/stats.jsonl.gz` with `symbol`,
`monthEnd` (last session), `close`, `medianDollarVolume`. The weekly
refresh appends the latest month.

### M06-T03 Backtest engine

`backtest.py` runs in three phases. Phases A and B are chunked jobs.
Phase C fits in one invocation.

**Phase A, factor tables.** For each adjusted-price part (100
symbols): for each symbol and each month end from `firstScreenMonth`,
build the snapshot as of that month end and compute every factor,
`marketCap`, and the count of years of fundamentals history. Write
`backtests/<runId>/factors/part=<nnn>.jsonl.gz`.

**Phase B, monthly portfolios.** For each month end `d`:

1. Historical universe: symbols whose monthly stats and Phase A row at
   `d` pass the price, dollar-volume, market-cap and history rules of
   `register.universe`, plus the SIC exclusion. Sector comes from the
   current SIC code.
2. Composite and hard filters exactly as in the screen.
3. Portfolio: walk the ranking from the top, take a name unless its
   sector already has `maxNamesPerSector`, stop at `portfolioSize`.
   Equal weights.
4. Write `backtests/<runId>/holdings/month=<yyyy-mm>.json`.

**Phase C, returns.**

1. The portfolio chosen at month end `d` is bought at the close of the
   session `tradeDelaySessions` after `d` and held until the same
   point next month.
2. For each holding period and each name, from the two price series:
   `total = adj_end / adj_start - 1` and
   `price = split_end / split_start - 1`. The dividend part is
   `total - price`. Net return =
   `price + (1 - dividendWithholdingRate) * (total - price)`.
3. Portfolio period return = mean of the names' net returns (equal
   weight), minus costs: `turnover * 2 * costBpsPerSide / 10000`,
   where turnover is the share of the portfolio that changed (0 to 1).
   The first month's turnover is 1.
4. A name with no price at the end of the period (delisted or
   acquired) uses its last available price. Count these and report
   the count.
5. Benchmarks over the same periods: SPY gross (`total`), SPY net of
   withholding (same formula as step 2), and BIL as cash.
6. Chain period returns into three equity curves starting at 100.
7. Write `backtests/<runId>/equity.json` and the `BACKTEST#<runId>`
   row with the metrics of T04.

Job `backtest` (manual run only). The request body may set only
`portfolioSize` (10 to 40) for the sensitivity runs. Everything else
comes from the register.

Tests, on a fixture of six invented companies over eight months:

- A hand-computed two-month example reproduces the equity curve to
  1e-9.
- A fundamentals row filed one day after a month end changes that
  month's ranking only from the next month.
- Withholding lowers the return of a dividend payer and leaves a
  non-payer unchanged.
- Costs: full turnover in month one, zero when holdings do not change.
- The sector cap skips the sixth name of a sector.
- A delisted name is carried at its last price and counted.

### M06-T04 Metrics

`backtest_metrics.py`, each a pure function with a hand-checked test:

- `cagr(curve)`: `(end / start) ** (12 / months) - 1`.
- `annualised_volatility(period_returns)`: population standard
  deviation times `sqrt(12)`.
- `sharpe(period_returns, cash_returns)`: mean of the excess returns
  over their standard deviation, times `sqrt(12)`.
- `max_drawdown(curve)`: largest fall from a previous high, as a
  negative fraction, with start and end months.
- `hit_rate(a, b)`: share of periods where `a` beat `b`.
- `worst_window(curve, months=12)`.
- `average_turnover(turnovers)`.
- `yearly_table(curve_a, curve_b)`: calendar-year returns side by
  side.

### M06-T05 Runs and memo

1. Run `backfill_monthly_stats`, then `backtest` with the register's
   settings. Then two sensitivity runs with `portfolioSize` 15 and 30.
   These three runs are the only runs. If a bug is found, fix it, say
   so in the memo, and rerun all three.
2. Write `docs/research/backtest-2017-2026.md` from the research
   template. It must contain:
   - The register hash and the three run ids.
   - A table: strategy net, SPY net, SPY gross, for the full period,
     2017 to 2021 and 2022 to today: CAGR, volatility, Sharpe, maximum
     drawdown.
   - The yearly table.
   - Hit rate, worst 12 months, average turnover, estimated yearly
     cost drag, count of names carried at a last price.
   - The sensitivity table for 15, 20 and 30 names.
   - The "Known biases" section below, with the answer to M04-T01
     question 3.
   - A plain verdict in the first paragraph: did the screen beat SPY
     net over the full period and over the holdout, yes or no.
3. Post the memo link in chat. If the verdict is no on either period,
   stop. The owner decides what happens next.

### M06-T06 API and dashboard

Routes (red: ask first): `GET /screens/latest`, `GET /screens/{date}`,
`GET /backtests`, `GET /backtests/{runId}`.

`LineChart.tsx`: a small SVG chart. Props: series (name, colour,
points of `{ x: string, y: number }`), height, a y-axis formatter. It
draws axes with five ticks, one path per series, a legend, and a
title for screen readers. No dependency. Test: it renders one path per
series and handles an empty series.

`ScreenPage.tsx` with two tabs (`AdminTabList`):

- **Shortlist**: date, register hash, counts (universe, passed
  filters, shortlisted). A sortable table: rank, symbol, name, sector,
  composite, the three group scores, each factor. A row opens to show
  the raw factor values and z-scores.
- **Backtest**: run selector; the three equity curves; the metrics
  table for the three periods; the yearly table; the bias notes.

Nav entry "Screen" (`bi-funnel`), mock fixtures, unit tests, smoke
test line.

## Known biases to state in the memo

- **Survivorship.** A name keeps the CIK from the latest stored
  universe file that still listed it. A name that was never in one of
  those files has no fundamentals, even when its price bars exist.
  Missing losers make the backtest look better than reality.
- **Sector and SIC code are the latest stored codes**, not the codes
  at the time.
- **Shares outstanding** come from filings and can lag buybacks and
  issues by a quarter.
- **Trading at the close with a fixed cost** ignores market impact.
  The universe is liquid, so this is small, not zero.
- **Dividend withholding is approximated** from the gap between two
  price series over each holding period.
- **Ten years is one market regime and a bit.** Most of it was a bull
  market led by large technology companies.
- **Two debt totals.** When a filing has only `LongTermDebt` and
  `DebtCurrent`, total debt is the larger figure. Borrowings that were
  never inside `LongTermDebt` are missed. Adding both totals would
  count the current portion twice.
- **Fallback debt tags** (notes, convertibles, other long-term debt,
  commercial paper, and the lease-inclusive total) apply only when the
  narrower tag is missing, and they are not added together.

## Done when

- Engine unit tests pass.
- The three runs exist and the Screen page shows them.
- The memo is merged and the owner has replied to it in chat.
- The `screen` job has produced a shortlist for the latest session.

## Rollback

Revert. Stored backtest files are harmless.

## Open questions

- If the verdict is negative: change the factor set from the books
  (after M07), or accept a lower aim. Owner's call.
