# Plan: Point-in-time shares and a wider price history

**Status**: Done
**Zone**: yellow

## Goal

A past month uses the share count that was public that day. The screen keeps only the adjusted closes the trend factors read. The backtest drops an unfinished month and does not exit after the newest stored bar. Adjusted prices include every name that cleared the price and dollar-volume floors in any month since February 2017 and still has a CIK.

## Non-goals

No live backtest, no `backfill_fundamentals`, and no deploy. Delisted names with no current CIK stay out. The two-total debt formula stays as it is.

## Files

- `backend/lambda/engine/backtest_inputs.py`, `backtest.py`, `backtest_job.py`, `screen.py`, `market_files.py`, `monthly_stats.py`, `ingest_jobs.py`
- Their tests
- `apps/admin_web/src/pages/ScreenPage.tsx`
- `docs/plans/06-screen-and-backtest.md`, `docs/research/methodology-provisional.md`

## Invariants this change preserves

Filings dated after the month end stay out of that month. A split still adjusts the count that was public. Trend factors still read 253 closes ending on the screen date, with a gap filled from the previous close. A complete month whose exit bar exists is unchanged. Today's universe members stay in the adjusted refresh.

## Done when

Engine unit tests cover a later share filing, the trimmed closes, a partial final month, and a historically liquid name that is not a member today. Admin unit tests pass. The Screen page states the remaining delisted-name bias.

## Rollback

Revert the commit. Adjusted files written for the wider symbol list can stay; they are unused until a backtest reads them.

## Open questions

None. Delisted names stay excluded until a historical ticker map exists.
