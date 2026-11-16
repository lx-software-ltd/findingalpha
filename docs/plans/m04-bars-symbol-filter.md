# Plan: Leave Alpaca's placeholder identifiers out of the bars request

**Status**: Draft
**Zone**: yellow

## Goal

Let `backfill_prices` get past its first month.

Alpaca's inactive asset list carries names that are not tickers, and the bars endpoint rejects each one as an invalid symbol. Two runs on 16 Nov 2026 showed four kinds:

- The 6:31 PM HKT run failed on `03211Q127`. It had skipped 20 nine-character identifiers for rights, contingent value rights, and escrow shares, such as `003CVR016`.
- The first version of this plan dropped nine uppercase characters ending in a digit. The 6:45 PM HKT run dropped 276 of them and failed on `C032597`. It had skipped the same identifiers in lowercase, one ending in letters (`92556PCAL`), a letter followed by six digits (`B002455`), and delisted names (`ABCD_DELISTED`, `B009988_DELISTED`).

All 42 rejected symbols contain a digit or an underscore. Every symbol the second run sent before `C032597` and did not skip was accepted. So the rule is now: a symbol with a digit or an underscore is not sent for bars. It applies to a symbol list saved in the job state too.

A symbol that is kept but is not letters and dots is still sent. The run logs how many there are and the first ten, so the next run answers the open question below.

## Non-goals

- Raising or removing the 20-skip cap. It stopped both runs for the right reason.
- Changing `reference/symbol-reuse.json`, the universe rules, or the exchanges that are priced.
- Dropping a dotted ticker such as `GUT.RT` or `KCA.U`.

## Files

- `backend/lambda/engine/ingest_prices.py` and `test_ingest_prices.py`
- `docs/plans/04-data-ingest.md`

## Invariants this change preserves

- SPY is always requested. BIL is always in the adjusted history.
- A symbol made of letters and dots is always sent.
- Any other symbol Alpaca rejects is still split out and skipped, and more than 20 new skips still fail the request.
- The month cursor and the saved window are unchanged.

## Done when

- `python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
- `python3 -m ruff check backend/lambda scripts .cursor/hooks`
- `python3 scripts/check_file_length.py`
- `python3 scripts/check_pii.py`

## Rollback

Revert the pull request. The backfill goes back to failing on the first month.

## Open questions

Whether Alpaca rejects a symbol that has neither a digit nor an underscore. The two runs covered every digit-leading symbol and the letters up to `C03`, and found none. The asset list itself was not read, so the rest of the alphabet is unchecked. If more than 20 such symbols exist, the month fails and the error names one.
