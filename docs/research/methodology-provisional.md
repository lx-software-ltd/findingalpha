# Provisional methodology

**Status**: In review
**Zone**: red for the register, yellow for the factor code

These formulas are textbook definitions so the screen can be built
before the knowledge base exists. Every entry is `provisional`. In M07
each one is matched against the owner's books, and the books win.

The owner asked to develop M05 on the values below, including the open
choices.

## Factors in the composite

| Id | Group | Direction | What it measures | Formula |
| --- | --- | --- | --- | --- |
| `roic` | quality | higher | How much operating profit the capital in the business produces, after tax | `NOPAT_ttm / average(investedCapital)` |
| `grossProfitability` | quality | higher | Gross profit relative to the asset base | `grossProfit_ttm / avg(totalAssets)`, or revenue minus cost when gross profit is missing |
| `fcfMargin` | quality | higher | The share of revenue that remains as cash after capital spending | `(operatingCashFlow_ttm - capex_ttm) / revenue_ttm` |
| `accruals` | quality | lower | Profit that has not turned into operating cash | `(netIncome_ttm - operatingCashFlow_ttm) / avg(totalAssets)` |
| `netDebtToEbitda` | quality | lower | Debt left after cash, against operating profit plus depreciation | `(longTermDebt + shortTermDebt - cash) / (operatingIncome_ttm + depreciationAmortization_ttm)` |
| `interestCoverage` | quality | higher | How many times operating profit covers interest | `operatingIncome_ttm / interestExpense_ttm`, capped at 100. The cap also applies when interest is zero or missing and debt is zero |
| `earningsYield` | value | higher | Operating profit against the whole firm value | `operatingIncome_ttm / enterpriseValue` |
| `fcfYield` | value | higher | Free cash flow against the whole firm value | `(operatingCashFlow_ttm - capex_ttm) / enterpriseValue` |
| `momentum12_1` | trend | higher | The price change from a year ago, skipping the last month | `close[t-21] / close[t-252] - 1` |
| `aboveSma200` | trend | higher | How far the price sits above its 200-session average | `close[t] / mean(close[t-199..t]) - 1` |

`enterpriseValue` is market cap plus long-term debt plus short-term debt
minus cash. It is missing when that total is not positive.
`average(investedCapital)` is the average equity plus the average of
each debt stock minus the average cash.

## Reported, and left out of the composite

| Id | What it measures | Formula |
| --- | --- | --- |
| `volatility252` | How widely the daily price moves, annualised | Standard deviation of 252 daily log returns, times `sqrt(252)` |
| `freeCashFlow_ttm` | Cash from operations after capital spending | `operatingCashFlow_ttm - capex_ttm` |

Their group is `reported`. The composite weights do not name that
group, so a missing value there does not block a company.

## Composite and screen

Group weights are quality 0.4, value 0.3, trend 0.3. Each factor is
winsorised at the 2.5th and 97.5th percentiles, then turned into a
z-score inside its sector. A sector with fewer than 10 values uses the
whole universe. A group with fewer than half its factors present scores
as missing, and the company gets no composite. The screen keeps
companies with positive trailing operating income, positive free cash
flow, and net debt to EBITDA of at most 4 (net cash passes). The
shortlist is 60 names.

## Open choices

- Group weights 40/30/30.
- The debt ceiling of 4.
- The shortlist of 60.
- Whether the books name factors that are not in this list. That is
  settled in M07, when each entry is cited or replaced.
