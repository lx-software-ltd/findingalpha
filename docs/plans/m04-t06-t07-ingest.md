# Plan: M04 price ingest and SEC ingest

**Status**: In review
**Zone**: yellow

## Goal

Store one raw price file and one corporate-action file per session, the
adjusted history in parts, and the SEC filings, trimmed company facts,
and news the later jobs read.

## Non-goals

- No universe build (T08).
- No job registration, schedule, or route (T09, red).
- No live backfill. T11 runs that after the switch is on.

## Files

- `backend/lambda/engine/ingest_prices.py` and `test_ingest_prices.py`
- `backend/lambda/engine/ingest_fundamentals.py` and `test_ingest_fundamentals.py`
- `backend/lambda/engine/ingest_news.py` and `test_ingest_news.py`
- `backend/lambda/engine/s3io.py` (gzip JSON for the trimmed facts)
- `docs/research/data-sources.md` (future process dates)
- `docs/plans/04-data-ingest.md`
- `contracts/roadmap.json`

## Invariants this change preserves

- Raw and adjusted prices stay in different files. A second run writes
  the same keys.
- A failed quality check writes nothing for that day or month.
- `IngestEnabled` off means these modules send no request.
- Fundamentals keep the filing date. The trimmed facts file holds only
  the mapped tags.
- News files hold headlines, not article bodies.

## Corrections

- A company with no XBRL file (HTTP 404) is stored as empty facts and the
  backfill continues.
- A chunked run stores a digest of its list. The same list resumes. A
  different list starts over. The resume payload includes the saved
  `params`, so a later job handler can rebuild the call.
- Adjusted history writes `prices/manifest.json` and deletes part files
  past the current count when the run finishes.
- `daily(sessions=...)` reads the filings cursor and walks sessions
  after it. A date that is not a session is not requested. An empty
  index before the through date is stored as an empty day and the
  cursor moves on. An empty index on the through date still waits.
- `refresh_corporate_actions` rewrites ex-date files for a recent
  window, so a row that appears later still lands.
- Coverage sets `coverage` on an existing universe row. It does not
  create a row.
- A ticker with two asset ids is requested once and listed in
  `reference/symbol-reuse.json`.
- Corporate actions request 1,000 rows per page. The kill switch is
  checked once per call, then held for the Alpaca requests inside it.
- One `IngestDisabled` type is shared. News symbols are upper-cased. A
  bad `createdAt` is skipped. A stock value older than 450 days does
  not count as covered.

## Behaviour

Alpaca selects corporate actions by `process_date`, and it does return
rows whose process date is still in the future. On 16 November 2026 a
window through 30 November returned 968 rows, and Tuesday 16 February
2027 returned 6. For the ex-date 10 June 2024, one row was processed
three days before the ex-date and one was processed 51 days after.
Across the 968-row window, 967 lags were 75 days or less and one was
335. The fetch window is therefore seven days before the session
through 75 days after it. Rows are kept only when `exDate` is the
session. The 335-day outlier is outside the window.

The daily symbol list is active NYSE and NASDAQ, plus `SPY`. `SPY` and
`BIL` trade on ARCA, so they are not in that exchange list. The raw
backfill adds inactive NYSE and NASDAQ names (2,179 on the probe day,
beside 8,483 active). One calendar month is one chunk: bars for the
whole month are requested once per symbol batch, which keeps a month
of about 11,000 names inside one Lambda run.

## Done when

`python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
passes, and ruff is clean on the new modules.

## Rollback

Revert the pull request. Nothing in this change writes to a live bucket.

## Open questions

None. The long process-date tail (one row at 335 days in the November
2026 sample) is left outside the 75-day window on purpose.
