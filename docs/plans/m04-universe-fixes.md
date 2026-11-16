# Plan: Universe screen corrections

**Status**: Draft
**Zone**: yellow. Two new provisional thresholds in `contracts/methodology.json` (red). The sector table is unchanged.

## Goal

Stop the universe build from admitting the wrong companies, publishing a short list, or wiping the coverage report.

## Non-goals

- No change to the SIC ranges. They follow the SEC titles already approved, including gas utilities as Utilities. Where that differs from the usual sector standard, the owner still chooses.
- No job, schedule, or route (T09).
- No live build.

## Files

- `contracts/methodology.json` (two new universe keys)
- `backend/lambda/engine/universe.py`, `universe_data.py`, and their tests
- `backend/lambda/engine/fundamentals_pit.py` and `test_fundamentals_pit.py`
- Generated contract copies from `scripts/sync-contracts.py`

## Rules

Thresholds stay in the contract.

- Three annual reports means three 10-K filings, each counted once by its latest full fiscal year. Comparative columns inside one 10-K do not add years. A 10-K/A for the same year does not add a year.
- The latest of those filings must be within `maxAnnualReportAgeDays` (500, provisional). A filer who switched to foreign forms years ago drops out.
- Dollar volume uses the full `dollarVolumeWindowSessions` window. A new listing with only a few sessions fails that rule.
- One listing per CIK. The more liquid share class is the listing. Share counts filed together are summed. A repeated fact with the same count is not added twice.
- Market cap multiplies that total by splits whose ex-date is after the share-count date and on or before the build date, then by the listing's last close.
- A missing last price file, or a session list shorter than the window, raises and writes nothing.
- A finished refresh is required before a build with missing fundamentals writes. The refresh job is `universe_fundamentals_refresh`, so it does not move the backfill cursor.
- SIC lookups are cached under `reference/sic/`. A blank SIC fails the industry screen.
- The universe row is updated in place. Coverage already stored on it is left alone.
- `maxMemberDropFraction` (0.5, provisional) refuses a build smaller than half the previous finished build. The first build has no previous row.

## Invariants this change preserves

- A filing dated after the build date is invisible.
- Financial SIC codes 6000 to 6799 stay out.
- The universe row keeps `gsi1pk` / `gsi1sk`.

## Done when

`python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`, ruff, `python3 scripts/check-contracts.py`, and the file-length check pass.

## Rollback

Revert the pull request. No live bucket is written.

## Open questions

SIC titles that differ from the usual sector groups (gas pipelines, drug wholesale, homebuilders, lab instruments, miscellaneous business services) stay as mapped until the owner says otherwise.
