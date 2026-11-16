# Plan: System page data status

**Status**: Draft
**Zone**: yellow

## Goal

Show the latest universe, the count after each rule, the last raw
price date, fundamentals coverage, and backfill progress on the
System page. Each job the contract allows to be started by hand has
a Run now button behind a confirm dialog.

## Non-goals

- No change to sector mappings.
- No live universe build and no backfill.
- The page does not invent a last price date. The universe build
  stores the session it priced, and the page shows that date, or a
  dash when the row has none.

## Files

```
apps/admin_web/src/pages/SystemPage.tsx
apps/admin_web/src/pages/SystemPage.test.tsx
apps/admin_web/src/hooks/useSystemStatus.ts
apps/admin_web/src/lib/mock/routes/system.ts
apps/admin_web/src/lib/mock/fixtures.ts
backend/lambda/engine/api_handler.py
backend/lambda/engine/system_status.py
```

## Invariants this change preserves

- Run now posts only to `/jobs/{jobName}/run`. The API still returns
  404 for a job that is not in the manual allow-list.
- Switches, recent runs, and API keys stay on the same page.

## Done when

The System page test confirms a run and shows the fixture counts.
`GET /universe/latest` returns coverage and backfill progress.
`npm run test:unit` in `apps/admin_web` passes, and the engine tests
for the two handlers pass.

## Rollback

Revert the page, the mock route, and the two response fields.

## Open questions

None.
