# Plan: M05 methodology register and factor library

**Status**: Draft
**Zone**: red (`contracts/methodology.json`). The factor code is yellow.

## Goal

Write down every formula and threshold the system uses in one file,
`contracts/methodology.json` (the register), and implement each formula
as a small, pure, unit-tested Python function. From this milestone on,
no number that affects money exists anywhere else.

## Non-goals

- No ranking of real companies yet (M06).
- No portfolio, leverage, exit or tax rules. Those sections are added
  to the register in M09.
- No citations yet. The knowledge base does not exist until M07. Every
  entry starts as `provisional`.
- No formula the owner has not seen. The list below is the proposal.

## The three layers, in practice

| Layer | Where | Who may change it |
| --- | --- | --- |
| Theory | Knowledge base (owner's PDFs) | Owner |
| Register | `contracts/methodology.json` | A red-zone pull request the owner approves |
| Code | `backend/lambda/engine/factors_*.py`, `composite.py` | Yellow-zone pull request, tests first |

A language model may read all three and may propose a register change
(M08). It may not change any of them.

## Files

```
contracts/methodology.json                      (extend)
backend/lambda/engine/methodology.py            test_methodology.py
backend/lambda/engine/snapshot.py               test_snapshot.py
backend/lambda/engine/factors_quality.py        test_factors_quality.py
backend/lambda/engine/factors_value.py          test_factors_value.py
backend/lambda/engine/factors_trend.py          test_factors_trend.py
backend/lambda/engine/composite.py              test_composite.py
backend/lambda/engine/test_fixtures/factor_golden.json
backend/lambda/engine/api_handler.py            (GET /methodology)
backend/infrastructure/lib/api-routes.ts        (red)
apps/admin_web/src/pages/MethodologyPage.tsx    (+ nav, mock, test)
docs/research/methodology-provisional.md
```

## Invariants this change preserves

- Every factor in the register has exactly one implementation, and
  every implementation is in the register. A test enforces both
  directions.
- Factor functions are pure: same input, same output, no network, no
  clock, no randomness.
- A missing input gives `None`. Never zero, never a guess.
- Code reads thresholds from the register. No threshold literal in a
  factor, composite or screen module.
- Every stored result carries the register hash it was computed with.

## Register shape

Add to `contracts/methodology.json`:

```json
{
  "version": 2,
  "factors": [
    {
      "id": "roic",
      "name": "Return on invested capital",
      "group": "quality",
      "direction": "higher",
      "formula": "NOPAT_ttm / average(investedCapital)",
      "definitions": {
        "NOPAT_ttm": "operatingIncome_ttm * (1 - taxRate)",
        "taxRate": "clamp(incomeTax_ttm / pretaxIncome_ttm, 0, maxTaxRate); defaultTaxRate when pretaxIncome_ttm <= 0 or missing",
        "investedCapital": "equity + longTermDebt + shortTermDebt - cash"
      },
      "parameters": { "maxTaxRate": 0.35, "defaultTaxRate": 0.21 },
      "implementation": "factors_quality.roic",
      "status": "provisional",
      "citation": null
    }
  ],
  "composite": {
    "status": "provisional",
    "winsorisePercentiles": [2.5, 97.5],
    "standardise": "zscore_within_sector",
    "minSectorSize": 10,
    "groupWeights": { "quality": 0.4, "value": 0.3, "trend": 0.3 },
    "minFactorsPerGroupShare": 0.5,
    "citation": null
  },
  "screen": {
    "status": "provisional",
    "hardFilters": [
      { "id": "positiveOperatingIncome", "field": "operatingIncome_ttm", "op": ">", "value": 0 },
      { "id": "positiveFreeCashFlow", "field": "freeCashFlow_ttm", "op": ">", "value": 0 },
      { "id": "debtCeiling", "field": "netDebtToEbitda", "op": "<=", "value": 4, "passWhenNetCash": true }
    ],
    "shortlistSize": 60,
    "citation": null
  }
}
```

`citation`, once set in M07, is
`{ "document": "<file name>", "locator": "<page or section>", "quote": "<at most 200 characters>" }`.
`status` is `provisional` or `cited`.

## Proposed factors (provisional)

These are standard textbook definitions, chosen so the screen can be
built and tested before the knowledge base exists. In M07 each is
matched against the owner's books. Where the books define something
differently, the books win and the register changes.

`_ttm` means trailing twelve months from `fundamentals_pit.ttm`.
`avg()` is `fundamentals_pit.average_stock`. Prices are adjusted
closes. `t` is the screen date, counted in trading sessions.

| Id | Group | Direction | Formula |
| --- | --- | --- | --- |
| `roic` | quality | higher | As in the example above |
| `grossProfitability` | quality | higher | `grossProfit_ttm / avg(totalAssets)`. If `grossProfit` is missing use `revenue_ttm - costOfRevenue_ttm` |
| `fcfMargin` | quality | higher | `(operatingCashFlow_ttm - capex_ttm) / revenue_ttm` |
| `accruals` | quality | lower | `(netIncome_ttm - operatingCashFlow_ttm) / avg(totalAssets)` |
| `netDebtToEbitda` | quality | lower | `(longTermDebt + shortTermDebt - cash) / (operatingIncome_ttm + depreciationAmortization_ttm)`. `None` when the denominator is not positive |
| `interestCoverage` | quality | higher | `operatingIncome_ttm / interestExpense_ttm`, capped at `coverageCap` (100). Equals the cap when interest expense is zero or missing and debt is zero |
| `earningsYield` | value | higher | `operatingIncome_ttm / enterpriseValue`, where `enterpriseValue = marketCap + longTermDebt + shortTermDebt - cash`. `None` when enterprise value is not positive |
| `fcfYield` | value | higher | `(operatingCashFlow_ttm - capex_ttm) / enterpriseValue` |
| `momentum12_1` | trend | higher | `close[t-21] / close[t-252] - 1` |
| `aboveSma200` | trend | higher | `close[t] / mean(close[t-199..t]) - 1` |

Also defined, used by later milestones and not part of the composite:

| Id | Formula |
| --- | --- |
| `volatility252` | Standard deviation of daily log returns over 252 sessions, times `sqrt(252)` |
| `freeCashFlow_ttm` | `operatingCashFlow_ttm - capex_ttm` |

## Composite score

For one screen date, over all universe members:

1. Compute every factor. `None` stays `None`.
2. For each factor, clip values to the 2.5th and 97.5th percentiles of
   the non-`None` values (winsorising). Percentiles use linear
   interpolation.
3. For each factor, turn values into z-scores inside each sector:
   `(value - sector mean) / sector standard deviation` (population
   standard deviation). A sector with fewer than `minSectorSize`
   non-`None` values, or a zero standard deviation, uses the whole
   universe instead.
4. Multiply by -1 for factors whose direction is `lower`.
5. Group score = mean of the z-scores of the group's factors that are
   not `None`. If fewer than half of the group's factors have a value,
   the group score is `None`.
6. Composite = sum of group weight times group score. If any group
   score is `None`, the composite is `None` and the company cannot be
   shortlisted.

## Steps

### M05-T01 Owner review memo

Write `docs/research/methodology-provisional.md`: the two tables
above, one sentence per factor on what it measures, and the open
choices (group weights, the debt ceiling of 4, the shortlist size).
Post the link in chat and wait. Owner task O11. Apply the owner's
changes to the tables in this file before writing the register.

### M05-T02 Register file and loader

1. Extend `contracts/methodology.json` with `factors`, `composite`,
   `screen` as agreed in T01. Bump `version`.
2. `methodology.py`:
   - `load()` reads the bundled copy
     (`backend/lambda/engine/contracts/methodology.json`).
   - `validate(doc)` raises `MethodologyError` on: unknown top-level
     key; a factor without `id`, `group`, `direction`, `formula`,
     `implementation`, `status`; a duplicate id; a group weight sum
     that is not 1.0 within 1e-9; a percentile outside 0 to 100; a
     status that is not `provisional` or `cited`; `cited` without a
     citation.
   - `register_hash(doc)`: SHA-256 of the JSON dumped with sorted keys
     and no whitespace. First 16 hex characters.
   - Accessors: `factor(id)`, `parameter(factor_id, name)`,
     `composite()`, `screen()`, `universe()`.
3. `scripts/check-contracts.py` calls the same `validate`.
4. Tests: each validation error; the hash is stable under key
   reordering and changes when a value changes.

### M05-T03 Company snapshot

`snapshot.py`: `build(symbol, cik, date, pit_rows, adjusted_bars,
raw_close, shares_outstanding)` returns a plain dict with every
`_ttm` flow, every latest and average stock value, `marketCap`,
`enterpriseValue`, and the adjusted close series up to the date. It
uses only `fundamentals_pit.as_of(rows, date)` and bars dated on or
before the date. This is the single place where "as of" is applied.

Tests: a bar dated after the date is not in the series; a fact filed
after the date does not change any value.

### M05-T04 Factor functions

One function per factor, signature `def roic(s: dict, params: dict)
-> float | None`. Rules for every function:

- Read inputs from the snapshot only.
- Return `None` if any required input is `None`, or a denominator is
  zero or (where the table says so) not positive.
- Take parameters from `params`, which the caller reads from the
  register.
- The docstring repeats the register's formula text.
- No rounding.

Write the tests first. For each factor: a normal case checked against
arithmetic written out in the test; each missing input; a zero
denominator; the direction edge cases named in the table (net cash,
zero interest, negative pretax income).

Then the golden file. `test_fixtures/factor_golden.json` holds five
invented companies with full inputs and the expected value of every
factor, computed by hand in a spreadsheet and typed in. The test
compares to 1e-9. This file is the regression guard: a later change
to any factor must change the golden file in the same pull request,
and the reviewer sees it.

### M05-T05 Registry test

`test_methodology.py`: import each `implementation` path from the
register and assert it is callable; walk the three factor modules and
assert every public function is named in the register.

### M05-T06 Composite

`composite.py`: `percentile(values, p)`, `winsorise(values, lo, hi)`,
`zscores_within_sector(rows, factor_id, min_sector_size)`,
`group_scores(row)`, `composite(rows, register)`. `rows` is a list of
dicts with `symbol`, `sector` and the factor values. The function
returns the same rows with `z` values, group scores, `composite`, and
the register hash.

Tests: percentile against known values; winsorising clips both tails;
a sector of three falls back to the universe; a constant factor
(zero standard deviation) gives z-scores of zero; a `lower` factor is
flipped; a row with a missing group gets `None`; weights come from
the register (change the fixture register, the result changes).

### M05-T07 API and dashboard page

1. `GET /methodology` returns the register, the hash, and counts of
   `provisional` and `cited` entries.
2. Route in `api-routes.ts` (red: ask first).
3. `MethodologyPage.tsx`: a KPI row (entries, cited, provisional,
   register hash); a table of factors (name, group, direction,
   formula, parameters, status badge, citation); cards for composite
   and screen settings. Read-only.
4. Nav entry "Methodology" (`bi-journal-check`), mock fixture, unit
   test, smoke test line.

## Done when

- Engine unit tests pass, including the golden file and the registry
  test.
- `python3 scripts/check-contracts.py` passes.
- `rg -n '[0-9]+\.[0-9]+' backend/lambda/engine/factors_*.py backend/lambda/engine/composite.py`
  shows no threshold literal outside docstrings and tests. Paste the
  output in the pull request.
- The Methodology page shows every entry as provisional.
- The owner has approved the memo from T01 in chat.

## Rollback

Revert the pull request. No stored data depends on it yet.

## Open questions

- Group weights 40/30/30, the debt ceiling of 4, the shortlist of 60.
  For the owner in T01.
- Whether the owner's books prescribe factors not in the table.
  Settled in M07.
