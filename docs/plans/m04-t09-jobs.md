# Plan: ingest jobs, schedules, and run routes

**Status**: Draft
**Zone**: yellow for the engine. Red for `contracts/jobs.json`,
the schedules, and the two routes. The owner approved T09 with the
share-count work.

## Goal

Wire the four ingest jobs, let `tick` resume a filings refresh and the
universe facts refresh, and expose the manual run and the latest
universe.

The six review points are decided as follows:

- A resumed price backfill uses the `start` and `end` saved on the job.
- `tick` can route `ingest_filings_refresh#<date>`. The state row is
  deleted when that refresh finishes.
- `ingest_daily` calls `refresh_corporate_actions` for the seven days
  ending on the session.
- A filings catch-up with no cursor requests only the last five
  sessions it was given.
- A chunked ingest checks the kill switch before each item. The item
  in progress finishes. The rest waits with status `paused`.
- A non-positive price on a name other than SPY is dropped and the
  backfill month continues. A bad SPY bar still fails that day.

The universe facts refresh stores the build date. When `tick` resumes
it and the facts finish, the build runs for that date.

## Non-goals

- No live backfill and no change to the sector table.
- Exchange holidays are a session when the caller says they are. The
  jobs do not guess a holiday calendar.

## Files

```
contracts/jobs.json
backend/lambda/engine/ingest_jobs.py       test_ingest_jobs.py
backend/lambda/engine/jobs_handler.py      test_jobs_handler.py
backend/lambda/engine/api_handler.py       test_api_handler.py
backend/infrastructure/lib/schedules.ts
backend/infrastructure/lib/api-routes.ts
docs/plans/reference.md
```

## Invariants this change preserves

- A job that is switched off writes `skipped_disabled` and does no work.
- A manual run of a job that is not allowed is 404.
- Headers and the contact stay out of logs.
- The engine, not the admin Lambda, does the long work.

## Done when

Engine unit tests, ruff, contract check, file length, and PII check
pass. CDK `npm test` and `npm run build` pass.

## Rollback

Revert the commit. Turning `IngestEnabled` off skips the next item.
