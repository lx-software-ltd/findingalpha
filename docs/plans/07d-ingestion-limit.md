# Plan: Let a knowledge base sync run for a day

**Status**: Implemented
**Zone**: yellow

## Goal

The first sync of 131 books was still running after several hours. Raise
the automatic stop from 6 hours to 24 hours, measured from `jobStartedAt`,
so a long ingestion is not marked failed while Bedrock is still working.

## Non-goals

- Changing the owner Stop button.
- Restarting the sync that is already running. The new limit applies on
  the next poll after this code is deployed.

## Files

- `backend/lambda/engine/kb_sync_jobs.py`
- `backend/lambda/engine/test_kb_sync.py`
- `docs/plans/07-knowledge-base.md`

## Invariants this change preserves

- A running ingestion is polled, not started again.
- The owner can still stop a sync.
- A failed or stopped ingestion keeps the last manifest.

## Done when

`python3 -m unittest backend.lambda.engine.test_kb_sync` passes, including
a job younger than 24 hours staying in progress and an older one being
stopped.

## Rollback

Revert the commit. The next poll then stops an ingestion that has been
running for 6 hours.

## Open questions

None.
