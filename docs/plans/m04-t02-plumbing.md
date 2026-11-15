# Plan: M04 plumbing

**Status**: Done. Merged in pull request 8. Follow-ups are in `m04-t02-followups.md`.
**Zone**: yellow. One red line: `EngineFn` may invoke itself so a
stalled chunked job can be started again.

## Goal

The shared pieces later ingest jobs use: HTTP with retries and a rate
limit, secret reads that are not logged, gzipped JSONL in the data
bucket, a cached trading calendar, and a cursor that survives the
15 minute Lambda limit.

## Non-goals

- No call to Alpaca or the SEC. That spike needs the paper key (O10)
  and is still M04-T01.
- No prices, fundamentals, news, or universe files.
- No new schedule and no new HTTP route.

## Files

- `backend/lambda/engine/http_client.py` and `test_http_client.py`
- `backend/lambda/engine/secrets_read.py` and `test_secrets_read.py`
- `backend/lambda/engine/s3io.py` and `test_s3io.py`
- `backend/lambda/engine/market_calendar.py` and `test_market_calendar.py`
- `backend/lambda/engine/chunked.py` and `test_chunked.py`
- `store.update_conditional` for the lease
- `jobs_handler._tick` calls `chunked.resume_stalled`
- `EngineFn` is granted `lambda:InvokeFunction` on itself through a
  separate policy, so the function does not depend on its own ARN

## Invariants this change preserves

- Headers and secret values are never logged.
- A secret that is missing or lacks a required key raises
  `NotConfigured` and is not cached.
- A second caller does not take a live lease.
- A failed item keeps the cursor and marks the job `failed`.
- `IngestEnabled` is untouched. These modules make no provider call.

## Done when

`python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
passes, and `ruff check` is clean on the new modules.

## Rollback

Revert the pull request. No data is written until a later job runs.

## Open questions

M04-T01 is blocked until the Alpaca paper key is in
`findingalpha/alpaca-paper`. The clients in T03 and T04 wait for that
memo.
