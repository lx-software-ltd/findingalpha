# Plan: M04 universe

**Status**: In review
**Zone**: red (`contracts/methodology.json`, `contracts/sic-sectors.json`). The build is yellow.

Corrections after review are in `docs/plans/m04-universe-fixes.md`: annual years are per 10-K filing, one listing per company, and a short or collapsed build is not written. The sector ranges are unchanged.

## Goal

Build the list of stocks the screen may consider, and record how many
names each rule removed.

## Non-goals

- No job, schedule, or route (T09).
- No System page section (T10).
- No live build. The first real size check is T11. If that size is
  outside 800 to 2,000, stop and ask.

## Files

- `contracts/methodology.json` (version and the universe section only)
- `contracts/sic-sectors.json`
- `backend/lambda/engine/universe.py` and `test_universe.py`
- Generated contract copies from `scripts/sync-contracts.py`

## Invariants this change preserves

- Thresholds are read from the contract. The code does not hardcode them.
- A filing dated after the build date is invisible.
- The universe row keeps `gsi1pk` / `gsi1sk` and any coverage already stored.
- Financial SIC codes 6000 to 6799 stay out. Their formulas are a later question.

## Rules

These values are provisional. The owner reviews them before the first live build.

- Marginable, because the book uses leverage.
- A 10-K, because a 20-F filer's tags are not the ones the formulas use.
- SIC 6000 to 6323 and 6325 to 6799, because banks, insurers, funds, and property trusts do not fit the quality formulas. SIC 6324 stays in. The confirmed split is `docs/plans/m04-sector-decisions.md`.
- Price at least $5, median dollar volume at least $20 million over 60 sessions, and market cap at least $2 billion, so trading costs stay small.
- Three annual reports already on file.

Sectors are the eleven groups named in the ingest plan, plus `Other` when a code matches no range. The ranges follow the SEC SIC list of 3 June 2021 (page reviewed 18 June 2026). Oil and gas, coal, and royalty traders are Energy. Drugs, medical devices, and health services are Health Care. Software, computers, and semiconductors are Technology. Banks and insurers are Financials. REITs and real estate operators are Real Estate. Electric, gas, and water utilities are Utilities. Publishing, telecom, and broadcasting are Communication. Codes 1 to 99 and anything above 9999 are `Other`.

## Done when

`python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
passes, ruff is clean, and `python3 scripts/check-contracts.py` passes.

## Rollback

Revert the pull request. No live bucket is written.

## Open questions

The four sector decisions are confirmed in `docs/plans/m04-sector-decisions.md`. Price, volume, and size stay provisional.
