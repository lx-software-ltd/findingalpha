# Plan: honest job runs and the same key actions

**Status**: In review
**Zone**: yellow, plus `contracts/jobs.json` and the production parameter file (red)

## Goal

A chunk that stops with time left is recorded as `partial`, with the
cursor, instead of `succeeded`. A job that returns `missing_inputs` is
recorded as `failed`. The system status includes each job's saved
position, and the System page shows it beside the last run. A missing
price file names the session and `backfill_prices`.

An API key with `operate` and `allowWrite` can start `ingest_daily`,
`backfill_prices`, and `backfill_fundamentals`. It cannot start
`weekly_refresh` or restart a backfill that has already finished.
The production parameter file sets `PublicApiWritesEnabled` to
`true`. The key list stays on the dashboard.

## Non-goals

- A key still cannot turn a switch on, tick an owner task, reset a
  breaker, or start a broker or drill job.
- The CloudFormation default of `PublicApiWritesEnabled` stays
  `false`. A key write still needs the parameter, `allowWrite`, and
  `operate`.
- No change to how tick resumes a `running` state row.

## Files

```
backend/lambda/engine/job_runs.py
backend/lambda/engine/jobs_handler.py
backend/lambda/engine/system_status.py
backend/lambda/engine/universe.py
backend/lambda/engine/api_handler.py
backend/lambda/engine/test_job_runs.py
backend/lambda/engine/test_jobs_handler.py
backend/lambda/engine/test_dashboard.py
backend/lambda/engine/test_universe.py
backend/lambda/engine/test_public_api.py
contracts/jobs.json
apps/admin_web/src/pages/SystemPage.tsx
apps/admin_web/src/hooks/useSystemStatus.ts
apps/admin_web/src/lib/mock/fixtures.ts
docs/plans/reference.md
docs/plans/11-safety-and-go-live-gate.md
docs/architecture/security.md
```

## Invariants this change preserves

- A raised exception is still `failed` with the error class, and the
  exception still propagates.
- `skipped_disabled` is unchanged.
- A finished chunk (`done`) is still `succeeded`.
- Broker and drill jobs stay `keyRun: false`.
- A key still cannot turn a switch on.
- The key list still omits the digest and the table key.
- `partial` is neither a success nor a failure for the M11 success rate.

## Done when

Engine unit tests cover a continuing chunk, a missing-inputs result, a
saved cursor on system status, the price-file message, and a key
starting `backfill_prices` while `breaker_drill` stays refused.
Admin unit tests cover the position text. `npm run dev:mock` shows the
position on the System page. `ruff` and the contract check pass.

## Rollback

Revert this change. New runs go back to `succeeded` whenever the
invocation returns. `ingest_daily`, `backfill_prices`, and
`backfill_fundamentals` go back to `keyRun: false`. The production
file sets `PublicApiWritesEnabled` back to `false`. `weekly_refresh`
and `GET /api-keys` stay as they are on main.

## Open questions

None.
