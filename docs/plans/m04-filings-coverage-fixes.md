# Plan: Filings catch-up and coverage numbers

**Status**: In review
**Zone**: yellow

## Goal

A filings catch-up moves past an exchange session whose SEC daily index
never appears, and the coverage report can be stored on the universe row.

## Non-goals

- No job registration, schedule, or route. T09 still has to reuse the
  saved backfill dates, route `ingest_filings_refresh#<date>`, call
  `refresh_corporate_actions`, and bound the first filings walk.
- No change to the kill switch or to the rule that one bad bar fails
  the month. Those are notes for the first run.
- No universe file and no live backfill.

## Files

- `backend/lambda/engine/ingest_fundamentals.py`
- `backend/lambda/engine/test_ingest_fundamentals.py`
- `backend/lambda/engine/test_ingest_prices.py` (the stand-in store
  rejects a float the way DynamoDB does)

## Invariants this change preserves

- A single day whose index is empty is still not ready. Nothing is
  written and the cursor stays.
- The through date of a catch-up is still not ready when its index is
  empty, because that file can appear later the same evening.
- Coverage still updates an existing universe row and leaves a missing
  row absent.
- A stock older than 450 days still does not count.

## Behaviour

The SEC publishes no master index on days it is closed while the
exchange is open. 14 October, 11 November, and 24 December 2024 are
three of those sessions. A catch-up that treats every empty index as
"not published yet" stops on the first one and never reads a later
session.

During a catch-up, an empty index on a session before the through date
is a closed day. The day is stored as an empty filings file, the cursor
moves to that session, and the walk continues. An empty index on the
through date itself still waits.

Coverage shares are `Decimal` values. DynamoDB's serializer rejects a
Python float, and the stand-in store now runs that serializer.

## Done when

`python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
passes, and ruff is clean on the edited modules.

## Rollback

Revert the pull request. No live bucket is written.

## Open questions

None. Waiting only on the through date is enough, because the next run's
through date is later and a closed day is then before it.
