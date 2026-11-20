# Plan: Cite the methodology register

**Status**: Approved
**Zone**: red. `contracts/methodology.json` is the register. Validation, the winsorise rule, the methodology route, and the admin page are yellow.

## Goal

Give every register entry a status of `cited` or `owner_accepted`, and clip composite factors to the mean ± a positive number of population standard deviations before the within-sector z-score.

## Non-goals

- Changing the 12 factor formulas, or `test_fixtures/factor_golden.json`.
- Running the screen or the backtest. Scores change with the winsorise rule; that rerun is after deploy.
- Marking M07-T06 done, or doing M07-T07.
- Adding the textbooks to the repository or to CI.

## Files

- `contracts/methodology.json` (red), then `python3 scripts/sync-contracts.py`.
- `backend/lambda/engine/methodology.py` and `test_methodology.py`.
- `backend/lambda/engine/composite.py` and `test_composite.py`.
- `backend/lambda/engine/api_handler.py` and `test_api_handler.py`.
- `apps/admin_web` methodology page, hook, mock fixture, unit test, and the methodology smoke line.
- `scripts/check_methodology_quotes.py`. It reads a local PDF directory and is not part of CI.
- `docs/plans/reference.md`: the methodology route counts.

## Invariants this change preserves

- Factor formulas and their golden values stay as they are.
- Missing factor values stay missing through winsorising.
- A `cited` entry still needs a document, a locator, and a quote of at most 200 characters.
- `owner_accepted` needs an `acceptedNote` of 1 to 300 characters. A citation on that entry, when present, follows the cited rules.
- `winsoriseStdDevs` is a number above 0. The register value is 3.
- The page shows the note when an entry has no quote, and shows the note and the quote when it has both.

## Register decisions

`freeCashFlow_ttm` is `cited`. The page 315 sentence is the capital-expenditure-only variant the register uses.

`volatility252` and `aboveSma200` are `owner_accepted` with citations. The volatility book divides by N−1; the register divides by N. The moving-average book describes a cross up through the average; the factor is the distance above it.

`roic`, `interestCoverage`, `earningsYield`, `momentum12_1`, and `composite` are `owner_accepted` with citations. The composite note records that within-sector z-scores and the group weights are an owner choice. Grinold & Kahn page 16 standardises across the stocks scored, and page 390 subtracts a capitalisation-weighted industry-average alpha.

The other entries are `owner_accepted` with a note and no citation. Citation `document` values are the PDF file names.

## Done when

- `python3 -m unittest backend/lambda/engine/test_methodology.py backend/lambda/engine/test_composite.py backend/lambda/engine/test_api_handler.py` passes.
- `python3 -m unittest scripts/test_check_methodology_quotes.py` passes.
- `npm test` in `apps/admin_web` passes.
- `python3 scripts/sync-contracts.py` and `python3 scripts/check-contracts.py` pass.
- The methodology page in `npm run dev:mock` shows the owner-accepted count, the winsorise sentence, a note with no quote, and a note with a quote.
- `python3 scripts/check_methodology_quotes.py <pdf-directory>` is run when the books are on the machine. This workspace does not have them.

## Rollback

Revert the commit. The register returns to version 5 and percentile winsorising. Screens already stored keep their old hash.

## Open questions

None.
