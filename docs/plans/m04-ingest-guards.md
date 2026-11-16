# Plan: ingest guards before the first run

**Status**: Done
**Zone**: yellow. The daily schedule hour in `contracts/jobs.json` and
`backend/infrastructure/lib/schedules.ts` is red, and this change is
the requested 12:00 Hong Kong time.

## Goal

Make the first live run measure coverage on the universe, write the
adjusted prices for those members, and ingest a session after the SEC
daily index exists. A key may start only a job marked `keyRun`. Run
now is offered only for a job the engine can run.

## Non-goals

- No live backfill and no change to sector mappings.
- The cover-page class sum still ignores conversion ratios.
- `contracts/roadmap.json` stays as it is.

## Files

```
backend/lambda/engine/ingest_jobs.py
backend/lambda/engine/universe.py
backend/lambda/engine/ingest_prices.py
backend/lambda/engine/api_handler.py
backend/lambda/engine/system_status.py
contracts/jobs.json
backend/infrastructure/lib/schedules.ts
docs/plans/reference.md
```

## Invariants this change preserves

- A saved backfill window is not recomputed.
- SPY and BIL stay in the adjusted history, including when the member list is empty.
- Tick does not start the adjusted refresh while this run still holds its lease.
- Reconcile, the daily check, and the brief run after `ingest_daily`.
- An empty news list writes no files.
- Broker and drill jobs stay `keyRun: false`.
- A dashboard user can still start `ingest_daily`.

## Done when

Engine unit tests cover member coverage, an adjusted job left running
when the coverage report stops, a resume that keeps the reused-ticker
file, news called with an empty list, and the key and Run now gates.
The schedule test expects 12:00 Hong Kong, Tuesday to Saturday.
`npm test` and `npm run build` pass in `backend/infrastructure`.

## Rollback

Revert this change. The daily schedule returns to 06:00 Hong Kong.

## Open questions

None.
