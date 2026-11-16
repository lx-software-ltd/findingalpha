# Plan: M04 Alpaca data client

**Status**: Done
**Zone**: yellow

## Goal

A client that reads the Alpaca paper asset list, SIP daily bars,
corporate actions, and news into the field names the later ingest jobs
use. The live shapes are the ones in `docs/research/data-sources.md`.

## Non-goals

- No price files, no job, and no schedule. Those are T06, T07, and T09.
- No call to the broker account endpoints.
- No change to `kill_switch.py`. T09 jobs check `ingestEnabled` before
  they call this module, the same way they will call `sec_edgar.py`.

## Files

- `backend/lambda/engine/alpaca_data.py`
- `backend/lambda/engine/test_alpaca_data.py`
- `backend/lambda/engine/test_fixtures/alpaca_*.json`
- `docs/research/data-sources.md` (already written)
- `contracts/roadmap.json` (M04-T03 done)

## Invariants this change preserves

- The paper secret is read at call time from `findingalpha/alpaca-paper`
  (`key_id` and `secret_key`). Headers and the secret stay out of the log.
- Daily bars use `feed=sip`. The spike showed the free plan returns SIP
  for past dates, including 2016, and that IEX has no 2016 bar.
- Bars are requested 200 symbols at a time and follow `next_page_token`.
- Raw and adjusted series stay distinct because `adjustment` is an
  argument (`raw`, `split`, `dividend`, `all`).
- News keeps `id`, `symbols`, `headline`, `summary`, `source`, `url`,
  and `createdAt`. The article body (`content`) is dropped.
- Calls stay at or under 150 a minute.

## Done when

`python3 -m unittest discover -s backend/lambda/engine -p 'test_alpaca_data.py' -v`
passes, and `python3 -m ruff check backend/lambda/engine/alpaca_data.py backend/lambda/engine/test_alpaca_data.py`
is clean. The engine suite still passes.

## Rollback

Revert the pull request. Nothing is stored. No schedule changes.

## Open questions

None for this client. The residual bias (delisted names Alpaca does not
list) is recorded in the spike memo for M06.
