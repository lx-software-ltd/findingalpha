# Plan: share count, closed-day index, and build guards

**Status**: Draft
**Zone**: yellow for the engine. Red for `contracts/fundamentals.json`,
which the owner approved with the share-count fix.

## Goal

Make the first universe build use a share count that survives the
three cases measured on the merged facts, and stop the build from
publishing an empty list or running past the Lambda limit.

- A cover-page count (`dei:EntityCommonStockSharesOutstanding`) is
  adjusted for splits after its `end` date. A balance-sheet count
  (`CommonStockSharesOutstanding`) is adjusted for splits after its
  `filed` date, because the statements restate the count. This is the
  date the owner settled for DP-01.
- A count whose `end` is more than 450 days before the build date is
  unused. The same limit is `STOCK_FRESH_DAYS` in the coverage report.
- When no fresh outstanding count exists, use the latest
  `WeightedAverageNumberOfDilutedSharesOutstanding` row. Two durations
  that share an `end` are not added. The split date is that row's
  `filed` date. This is DP-02.
- When that average is also missing, read the latest 10-K or 10-Q
  cover page and add the class counts of
  `dei:EntityCommonStockSharesOutstanding`. Companyfacts drops those
  dimensional facts. Visa's common classes are only on that page.
  Preferred stock is a different tag and is not included. The split
  date is the cover instant.
- A 403 on a daily master index is an empty day when that quarter's
  `index.json` does not list the file. A listed file that returns 403
  is still a failure.
- Any missing raw price file in the dollar-volume window fails the
  build before it writes. SIC lookups stop when the invocation has
  under two minutes left, and the build writes nothing so the cached
  codes can finish on the next run.

## Non-goals

- No change to the SIC sector table. Health insurers, Walmart,
  Costco, Visa, and Mastercard stay where the current table puts them
  until the owner answers.
- No first live universe build, and no T09 or T10 in this change.
- No compact `corporate-actions/splits.jsonl.gz` yet. The build still
  reads the per-session action files. The daily job can write the
  compact file when that job is wired.
- `shortTermInvestments` and `shareBasedCompensation` are stored with
  this contract bump and are not used in a formula. The precision
  plan asks for them in the same change so the fundamentals backfill
  does not have to run twice.

## Files

```
contracts/fundamentals.json
backend/lambda/engine/share_count.py          test_share_count.py
backend/lambda/engine/fundamentals_pit.py     test_fundamentals_pit.py
backend/lambda/engine/universe.py             test_universe.py
backend/lambda/engine/universe_data.py
backend/lambda/engine/sec_edgar.py            test_sec_edgar.py
backend/lambda/engine/http_client.py
backend/lambda/engine/ingest_fundamentals.py
docs/plans/04-data-ingest.md
```

## Invariants this change preserves

- Nothing uses a number before its `filed` date.
- A missing count drops the company. It is not treated as zero.
- Preferred shares are not a common share count.
- Issued shares are not used in place of outstanding shares.
- Headers and the contact address stay out of logs.
- A 403 for a file the quarter listing contains still raises.
- The sector map is unchanged.

## Done when

`python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`,
`python3 -m ruff check backend/lambda scripts .cursor/hooks`,
`python3 scripts/sync-contracts.py`, `python3 scripts/check-contracts.py`,
`python3 scripts/check_file_length.py`, and `python3 scripts/check_pii.py`.

## Rollback

Revert the commit. Stored companyfacts files that already dropped the
new tags need one fundamentals refresh before the new count can see
them. The universe members file from a previous build is left in place
when a build raises.

## Open questions

None for the split date. The owner set the balance-sheet rule.
