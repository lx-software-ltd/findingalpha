# Plan: SIC, a saved ticker map, and an honest price scope

**Status**: Done
**Zone**: yellow

## Goal

A name that was never in a universe file gets the SIC cached from SEC submissions and the sector of that SIC. A missing SIC excludes it, as the live universe does. A reused ticker with no universe row is left out. The backtest reads one saved ticker map and one saved membership table. The weekly result reports how many symbols the adjusted refresh will price, and says when monthly stats are missing. Monthly stats are rewritten when the universe build has finished, including when the adjusted refresh is still running, and again when that refresh finishes. A skipped past month counts as the calendar months it spans. Share counts fall back to a cached cover page that was already public.

## Non-goals

No live backtest, no `backfill_fundamentals`, and no deploy. The backtest does not download filing documents. Delisted names with no current CIK stay out. The two-total debt formula stays as it is.

## Files

- `backend/lambda/engine/backtest.py`, `backtest_inputs.py`, `backtest_job.py`, `backtest_metrics.py`, `monthly_stats.py`, `jobs_handler.py`, `ingest_jobs.py`, `screen.py`, `share_count.py`, `universe_data.py`
- Their tests
- `apps/admin_web/src/pages/ScreenPage.tsx` and its test
- `docs/plans/06-screen-and-backtest.md`, `docs/plans/m06-price-scope.md`, `docs/research/methodology-provisional.md`

## Invariants this change preserves

A symbol stored in a universe file keeps that file's CIK, sector, and SIC. Filings dated after the month end stay out of that month. A cover page is used only when the company-facts count is missing, and only when its filing date is on or before the month end. Today's members stay in the adjusted refresh. A complete month whose exit bar exists is unchanged.

## Done when

Engine tests cover a missing SIC, a mapped SIC, a reused ticker, one ticker-map snapshot, a missing monthly table, a monthly rewrite while adjusted prices are still running, a two-month gap in CAGR, and a cover page filed later. Admin unit tests pass. The Screen page states the remaining delisted-name bias.

## Rollback

Revert the commit. SIC and cover caches written under `reference/` can stay. A backtest run started on the new item list starts again, because the item digest changed.

## Open questions

None.
