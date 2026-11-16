# Plan: ingest review fixes

**Status**: Draft
**Zone**: yellow

## Goal

Make a scheduled or manual ingest run use the New York session that
has already closed, and load the calendar, assets, and ticker map when
the event does not carry them. An empty load is refused. A paused or
unfinished build can be resumed by tick, and only while ingest is on.
The System page still renders before the first universe exists.

## Non-goals

- No change to sector mappings.
- No live backfill.
- `refresh_adjusted` and `universe_build` are resume targets. They are
  not added to `contracts/jobs.json` and have no schedule.
- The weighted-average share count stays the fallback. It includes
  options and convertibles, so that market cap is a little high.

## Files

```
backend/lambda/engine/ingest_jobs.py
backend/lambda/engine/jobs_handler.py
backend/lambda/engine/chunked.py
backend/lambda/engine/market_calendar.py
backend/lambda/engine/universe.py
backend/lambda/engine/universe_data.py
backend/lambda/engine/share_count.py
backend/lambda/engine/sec_edgar.py
backend/lambda/engine/ingest_prices.py
backend/lambda/engine/ingest_fundamentals.py
backend/lambda/engine/api_handler.py
apps/admin_web/src/pages/SystemPage.tsx
```

## Invariants this change preserves

- A saved backfill window is not recomputed.
- A 403 for a file the quarter listing omits is still a closed day.
- Run now still posts only for a job the contract marks manual.
- An empty asset list does not publish a universe.

## Done when

The engine tests cover the Tuesday and Saturday clocks, a refused
empty build, a paused row that tick leaves alone while ingest is off,
and a cover page that skips an empty amendment. The System page test
renders when the universe payload has no backfill. `npm run test:unit`
in `apps/admin_web` passes.

## Rollback

Revert this change. Scheduled jobs return to taking New York's
yesterday and to running with whatever the event contains.

## Open questions

None.
