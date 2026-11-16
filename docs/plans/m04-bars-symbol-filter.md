# Plan: Leave Alpaca's placeholder identifiers out of the bars request

**Status**: Draft
**Zone**: yellow

## Goal

Let `backfill_prices` get past its first month.

The run at 6:31 PM HKT on 16 Nov 2026 failed with `HTTP 400 invalid symbol: 03211Q127`. The inactive asset list carries rights, contingent value rights, and escrow shares under a nine-character identifier that ends in a digit, such as `003CVR016`. The bars endpoint rejects each one. The run skipped 20 of them, one request or two apiece, and the 21st hit the skip cap. Symbols are sorted, so these all sit in the first batch.

Every symbol sent for bars now passes one filter that drops that shape. It applies to a symbol list saved in the job state too, so a tick resume of the failed run does not send them again.

## Non-goals

- Raising or removing the 20-skip cap. It stopped this run for the right reason.
- Changing `reference/symbol-reuse.json`, the universe rules, or the exchanges that are priced.
- Dropping any symbol that only looks unusual, such as `GUT.RT` or `KCA.U`.

## Files

- `backend/lambda/engine/ingest_prices.py` and `test_ingest_prices.py`
- `docs/plans/04-data-ingest.md`

## Invariants this change preserves

- SPY is always requested. BIL is always in the adjusted history.
- A ticker is never dropped by shape. The filter matches exactly nine characters, letters and digits only, ending in a digit. No NYSE or NASDAQ ticker has that form.
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

Whether Alpaca rejects any other kind of symbol in the inactive list. The filter is built from the 21 rejected symbols in the log and the three identifiers in `reference/symbol-reuse.json`. If more than 20 symbols of another shape are rejected, the month fails and the error names one of them.
