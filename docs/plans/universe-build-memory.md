# Plan: Universe build fits in one run

**Status**: Done
**Zone**: yellow

## Goal

The weekly universe build must finish on the 2 GB engine, and a run that stops must be resumed by tick. The build keeps one company's facts at a time, checks the clock while it reads, and records the build job before that work starts.

## Non-goals

No live weekly run, no `backfill_fundamentals`, and no deploy. Membership rules, share-count sources, and the written universe row stay as they are.

## Files

- `backend/lambda/engine/universe.py`, `universe_screen.py`, `universe_data.py`, `ingest_jobs.py`
- `backend/lambda/engine/test_universe.py`, `test_ingest_jobs.py`

## Invariants this change preserves

A company is admitted or rejected by the same rules as today. A missing facts file still starts `universe_fundamentals_refresh` and writes nothing. A stopped build writes nothing. The facts refresh remains the job tick resumes while it is open. A hard stop leaves a `universe_build` row tick can resume after the lease. A graceful stop leaves that row without a lease, and the next run continues from the saved company.

## Done when

Engine tests show one company file is released before the next is read, a second company is not read once the clock is short, a later run continues from the saved company, a missing file is not downloaded, and the build job is saved with a lease before the build runs. `ruff` and the file-length check pass.

## Rollback

Revert the commit. A `universe/date=*/build.json` progress file can stay; the next build ignores it when the company list differs, and deletes it when the build finishes. A `universe_build` row left `running` waits for tick or Run now.

## Open questions

None.
