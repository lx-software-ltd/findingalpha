# Plan: owner sector decisions before the first run

**Status**: In review
**Zone**: red. `contracts/methodology.json`, `contracts/sic-sectors.json`, and `backend/infrastructure/params/production.json`. The build change is yellow.

The owner accepted these four decisions on 16 November 2026.

## Goal

Apply the four universe decisions, and turn the production ingest parameter on so the first run can start. The runtime switch stays off until the owner turns it on.

## Decisions

- Only SIC 6324 (hospital and medical service plans) stays in the universe, mapped to Health Care. SIC 6321 (accident and health insurance) stays out with the other insurers: two NYSE insurers file under that code. The exclusion is `[[6000, 6323], [6325, 6799]]`.
- SIC 5330 to 5399 (variety stores and miscellaneous general merchandise) map to Consumer Staples. Department stores (5311) stay Consumer Discretionary. Two variety-store filers that are discretionary retailers are listed by CIK and stay Consumer Discretionary: `0001177609` and `0001639300`.
- CIKs `0001403161` and `0001141391` map to Financials. Their SIC is 7389, which stays Industrials for every other company, because that code is business services in general. Exclusion is by SIC range, so these two stay in the universe. The override is by CIK, not by ticker.
- History still requires three distinct fiscal years, one per 10-K filing. A listing with only two 10-Ks stays out. Comparative columns in one filing still count as one year.

Price, volume, and size thresholds stay provisional.

## Non-goals

- No live backfill in this change. The first run is T11, after this deploys and the runtime switch is on. Leave that switch off until `backfill_prices` can be started: the Sunday refresh needs 60 sessions of price files.
- No change to cover-page conversion ratios or to how far a cover lookup reads.

## Files

- `contracts/methodology.json`
- `contracts/sic-sectors.json`
- `backend/lambda/engine/universe.py` and `test_universe.py`
- Generated copies from `scripts/sync-contracts.py`
- `backend/infrastructure/params/production.json`
- `contracts/roadmap.json` (T09 and T10 are already merged)
- `docs/plans/04-data-ingest.md`, `docs/plans/m04-t08-universe.md`, `docs/plans/reference.md`

## Invariants this change preserves

- A code still matches exactly one range, from 100 through 9999.
- Life insurance (6311), property insurance (6331), and banks (6021) stay excluded.
- Three distinct 10-K fiscal years are still required.
- SPY and BIL are unchanged. The other thresholds are unchanged.
- The CDK default for `IngestEnabled` stays `false`. Only the production params file changes.

## Done when

`python3 -m unittest backend.lambda.engine.test_universe` covers the four decisions. The engine suite, ruff, and `python3 scripts/check-contracts.py` pass.

## Rollback

Revert this change. Set `findingalpha:IngestEnabled` back to `false` and redeploy. Stored files stay.

## Open questions

None.
