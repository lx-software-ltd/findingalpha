# Plan: Universe build fits in one run

**Status**: Done
**Zone**: yellow

## Goal

The weekly universe build must finish on the 2 GB engine, and a run that stops must be resumed by tick. The build keeps one company's facts at a time, checks the clock while it reads, and records the build job before that work starts.

A build that raises, or that is killed three times, is marked failed with no failure count so tick waits for Run now. The company list is kept with the progress file. The members file is written only when time remains after the screen, and the coverage report is retried without screening again.

## Non-goals

No live weekly run, no `backfill_fundamentals`, and no deploy. Membership rules, share-count sources, and the written universe row stay as they are. `chunked._resumable` is unchanged.

## Files

- `backend/lambda/engine/universe.py`, `universe_screen.py`, `universe_data.py`, `ingest_jobs.py`, `ingest_job_state.py`
- `backend/lambda/engine/test_universe.py`, `test_ingest_jobs.py`
- `docs/plans/reference.md`

## Invariants this change preserves

A company is admitted or rejected by the same rules as today. A missing facts file still starts `universe_fundamentals_refresh` and writes nothing. A stopped build writes nothing. The facts refresh remains the job tick resumes while it is open. A graceful stop leaves `universe_build` running without a lease, and the next run continues from the saved company and the saved company list. A build that raises is marked failed with no `failures` field and is re-raised. A row left running with an expired lease can be resumed twice; the third expired lease is marked failed the same way. A second start does not run while the lease is still in the future. The adjusted refresh is leased before the coverage report.

## Done when

Engine tests show one company file is released before the next is read, a later run continues from the saved company, a missing file is not downloaded, and the build job is saved with a lease before the build runs. They also show a raised build is not resumed by tick, three hard stops stop the job, a live lease blocks a second start, a short clock after the screen writes nothing, and a short clock before the coverage report leaves the build running so the next run skips the screen. `ruff`, the file-length check, and the personal-data check pass.

## Rollback

Revert the commits. A `universe/date=*/build.json` file is the in-progress list for that date. A `universe_build` row left `failed` without a failure count waits for Run now. A row left `running` waits for tick after the lease.

## Open questions

None.
