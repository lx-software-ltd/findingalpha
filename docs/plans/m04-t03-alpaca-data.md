# Plan: M04 Alpaca data client

**Status**: In review
**Zone**: yellow

## Goal

A client that reads the Alpaca paper asset list, SIP daily bars,
corporate actions, and news into the field names the later ingest jobs
use. The live shapes are the ones in `docs/research/data-sources.md`.

## Non-goals

- No price files, no job, and no schedule. Those are T06, T07, and T09.
- No call to the broker account endpoints.
- No edit to `kill_switch.py`. This module calls `is_enabled` and does
  not change the switch.

## Files

- `backend/lambda/engine/alpaca_data.py`
- `backend/lambda/engine/test_alpaca_data.py`
- `backend/lambda/engine/test_fixtures/alpaca_*.json`
- `docs/research/data-sources.md` (already written)
- `scripts/probe_data_sources.py` (re-runs the spike; not part of CI)
- `contracts/roadmap.json` (M04-T03 done)

## Invariants this change preserves

- The paper secret is read on each call from `findingalpha/alpaca-paper`
  (`key_id` and `secret_key`). `secrets_read` may cache it for five
  minutes. Headers and the secret stay out of the log. A rotated key
  is picked up on the next call after that cache.
- `IngestEnabled` off means this module sends no request.
- Daily bars use `feed=sip`. The spike showed the free plan returns SIP
  for past dates, including 2016, and that IEX has no 2016 bar.
- Bars and news are requested 200 symbols at a time and follow
  `next_page_token`. A repeated token raises.
- Raw and adjusted series stay distinct because `adjustment` is an
  argument (`raw`, `split`, `dividend`, `all`).
- News keeps `id`, `symbols`, `headline`, `summary`, `source`, `url`,
  and `createdAt`. The article body (`content`) is dropped.
- Calls stay at or under 150 a minute across containers. The counter
  is the `RATE#alpaca` / `MINUTE` row in the records table. A process
  also spaces its own calls. With no records table, only that spacer
  applies.
- Corporate actions are selected by Alpaca on `process_date`. The
  client also returns `exDate`, `special`, `foreign`, `subType`, and
  `newSymbol`, and does not drop a row whose ex-date is outside the
  window.

## Done when

`python3 -m unittest discover -s backend/lambda/engine -p 'test_alpaca_data.py' -v`
passes, and `python3 -m ruff check backend/lambda/engine/alpaca_data.py backend/lambda/engine/test_alpaca_data.py`
is clean. The engine suite still passes.

## Rollback

Revert the pull request. Nothing is stored. No schedule changes.

## Open questions

None for this client. The residual bias (delisted names Alpaca does not
list) is recorded in the spike memo for M06.
