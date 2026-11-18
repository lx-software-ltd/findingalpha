# Plan: Knowledge base sync failure and confirmation fixes

**Status**: Implemented
**Zone**: yellow, plus one red IAM action approved in chat on 18 November 2026

## Goal

A failed or stuck ingestion can be retried, the last good manifest stays
in place while a sync runs, problem files are recorded and skipped, and
only the owner can confirm a deletion, stop a sync, or start the first
one.

## Non-goals

- Marking M07-T03 done. The roadmap row stays `todo` until the first
  real sync reports document counts.
- The Knowledge base page (M07-T08). Confirm and Stop live on System
  until that page exists.
- Changing `keyRun`. A key may still start a later sync.

## Files

- `backend/lambda/engine/kb_sync.py` and its tests
- `backend/lambda/engine/job_runs.py` and `test_job_runs.py`
- `backend/lambda/engine/api_handler.py`, `test_api_handler.py`,
  `test_public_api.py`
- `apps/admin_web/src/pages/SystemPage.tsx`, its test, and
  `useSystemStatus.ts`
- `apps/admin_web/src/lib/mock/routes/system.ts`
- `backend/infrastructure/lib/knowledge-base.ts` and the stack test
  (`bedrock:StopIngestionJob` only)
- `docs/plans/07-knowledge-base.md`, `docs/plans/reference.md`

## Invariants this change preserves

- The daily schedule does not start the first sync.
- A deletion above 15% in one data source syncs nothing until the
  owner confirms.
- A running ingestion is resumed by the tick, not started again.
- Run rows for other jobs are unchanged when their result has no error.

## Done when

- Engine unit tests, admin unit tests, and the infrastructure test and
  build pass.
- Ruff, the personal-data check, and the file-length check pass.

## Rollback

Revert the pull request. No stored row needs a migration: a state row
written by the previous build is still readable, and a missing
`jobStartedAt` simply does not time out.

## Open questions

None. The ingestion limit is 6 hours, then the handler calls
`StopIngestionJob` and the next run may start a new job.
