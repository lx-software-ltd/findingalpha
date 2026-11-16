# Plan: Fix the first ingest run

**Status**: Draft
**Zone**: yellow

## Goal

Make `tick` able to read job state, and make `backfill_prices` survive one dropped connection and one symbol Alpaca rejects.

The live run on 16 Nov 2026 showed three separate failures. `tick` has failed on every run since 15 Nov 9:51 PM HKT because `query_gsi1` sends `begins_with(gsi1sk, "")`, which DynamoDB rejects. The first `backfill_prices` died on a connection timeout before any file was written. The second, at 5:39 PM HKT, wrote the calendars and `reference/symbol-reuse.json`, then Alpaca answered HTTP 400 on the first daily-bars request. The response body was not kept, so the client now keeps Alpaca's `message` and splits a 400 down to one symbol.

## Non-goals

- Alarm email. The errors alarm has no action by the M02 plan; wiring one is infrastructure.
- Purging the dead-letter queue.
- Changing the symbol set, the sector map, or the ingest switch.

## Files

- `backend/lambda/engine/store.py` and `test_store.py`
- `backend/lambda/engine/http_client.py` and `test_http_client.py`
- `backend/lambda/engine/chunked.py` and `test_chunked.py`
- `backend/lambda/engine/alpaca_bars.py`, `alpaca_data.py`, `test_alpaca_data.py`
- `backend/lambda/engine/ingest_jobs.py` and `test_ingest_jobs.py`
- `docs/plans/04-data-ingest.md`, `docs/plans/reference.md`

## Invariants this change preserves

- A job still stops with two minutes left and keeps its cursor.
- Headers, secrets, and query strings stay out of logs and error text.
- SPY is never skipped. A 400 that SPY also gets fails the run.
- A skipped symbol is remembered by the client. More than 20 new skips in one bars request fail that request.
- Tick resumes a failed row only when `run()` wrote a failure count under three. A universe build marked failed, and a row written before this change, wait for Run now. After three counted failures, a later Run now that fails again is left alone.
- The resume message stays under 200 KB. A larger saved parameter block is read from the state row.

## Done when

- `python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
- `python3 -m ruff check backend/lambda scripts .cursor/hooks`
- `python3 scripts/check_file_length.py`
- `python3 scripts/check_pii.py`

## Rollback

Revert the pull request. State rows already written stay valid. `tick` goes back to failing the query, and a failed backfill waits for Run now.

## Open questions

None. If the next bars request fails for a reason other than one symbol, the run error includes Alpaca's message.
