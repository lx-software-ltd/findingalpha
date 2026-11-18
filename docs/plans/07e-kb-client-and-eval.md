# Plan: Retrieval client, evaluation, and empty prefixes

**Status**: Implemented
**Zone**: yellow, plus `contracts/budgets.json` approved in chat on 18 November 2026

## Goal

Code can retrieve passages under the monthly cap, and a manual job can
score `eval/questions.json`. A sync does not start an ingestion for a
prefix that has no files and had none last time.

## Non-goals

- Marking M07-T03 or M07-T05 done. T03 waits for the first real sync.
  T05 waits for that sync and for the hit targets.
- Marking M07-T07 done. The MCP file and the owner guide are written.
  The row stays `todo` until the owner creates the read-only profile
  and a query works.
- The Knowledge base page (M07-T08).
- Running a retrieval or an evaluation against the live knowledge base.

## Files

- `contracts/budgets.json` and the generated copies
- `contracts/roadmap.json` (M07-T04 done)
- `backend/lambda/engine/kb_client.py`, `kb_eval.py`, their tests
- `backend/lambda/engine/kb_sync.py` and `test_kb_sync.py`
- `backend/lambda/engine/jobs_handler.py`, `job_runs.py`, and their tests
- `.cursor/mcp.json`
- `docs/deployment/knowledge-base.md`
- `docs/plans/07-knowledge-base.md`, `docs/plans/reference.md`

## Invariants this change preserves

- No retrieval once the month is at 5,000. The counter increments once
  per call and not on a cache hit.
- Passage text is not logged and is not stored on the evaluation row.
- A prefix that previously had files still follows the 15% deletion rule.
- `kb_eval` has no kill switch. A missing switch on any other job is
  unchanged.

## Done when

Engine tests for the client, the evaluation, and the sync pass. The
contract check passes. The evaluation job is registered and its result
message is kept on the run row.

## Rollback

Revert the commit. The cap, the job, and the empty-prefix skip go away
together. A sync in progress is unaffected, because it is already past
the decision.

## Open questions

None. The budget values are the ones in the M07 plan.
