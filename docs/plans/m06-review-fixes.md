# Plan: M06 review fixes

**Status**: In progress
**Zone**: yellow for the engine and the Screen page. Red for `contracts/fundamentals.json`, edited because the review asked for the missing debt tags to be read.

## Goal

Make a backtest month use that month's price, liquidity, and share count, keep a CIK for a name that has left the latest universe file, and stop the screen and the backtest from rereading the whole price store once per name. Report the figures the memo needs, and state the debt-total bias.

## Non-goals

- No live backtest and no invented results.
- No change to the numeric debt split when only `LongTermDebt` and `DebtCurrent` are filed. That case is a stated bias.
- Fallback debt tags are alternatives. They are not added on top of a total that is already filed.

## Files

```
contracts/fundamentals.json
backend/lambda/engine/market_files.py
backend/lambda/engine/backtest_inputs.py
backend/lambda/engine/backtest.py
backend/lambda/engine/backtest_job.py
backend/lambda/engine/backtest_metrics.py
backend/lambda/engine/screen.py
backend/lambda/engine/monthly_stats.py
backend/lambda/engine/fundamentals_pit.py
backend/lambda/engine/methodology.py
backend/lambda/engine/snapshot.py
backend/lambda/engine/research_api.py
backend/lambda/engine/jobs_handler.py
apps/admin_web/src/pages/ScreenPage.tsx
apps/admin_web/src/components/ui/LineChart.tsx
docs/research/methodology-provisional.md
```

## Invariants this change preserves

- The screen and the backtest still call `snapshot`, the factor functions, and `composite`.
- A filing dated after the month end stays invisible for that month.
- Hard filters, sector cap, withholding, and the cost formula stay as specified.
- `unreportedDebt: zero` still applies in the snapshot, not in the raw rows.

## Done when

- Engine unit tests, admin unit tests, and the screen smoke pass.
- `python3 scripts/check-contracts.py` passes.

## Rollback

Revert. Stored backtest files from the previous shape are unused by the new paths.
