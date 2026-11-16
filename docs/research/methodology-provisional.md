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

Debt tags are combined per balance-sheet date. `LongTermDebt` already
includes `LongTermDebtCurrent`, and `DebtCurrent` already includes the
current portion and short-term borrowings, so those are not added
again. When only the two totals are filed, the smaller one is treated
as part of the larger one. That keeps the current portion from being
counted twice, and it misses borrowings that sit in `DebtCurrent` and
were never inside `LongTermDebt`. Adding both totals would make the
opposite mistake. A later filing that repeats an old column does not
hide the original filing date. The stored tag lists every tag used in
the combination.

Notes payable, convertible notes, other long-term debt, commercial
paper, and the lease-inclusive long-term total are read only when the
narrower tag for that role is absent. They are alternatives, not extra
dollars on top of a total. The lease-inclusive total includes leases.

The register says `unreportedDebt` is `zero`. A balance sheet that
never reports a debt tag, or that drops the tag after an older
statement, counts as zero of that debt. Coverage still counts only a
tag that was filed.

Closes follow the market session calendar. A session with no print
keeps the previous close, so a missing day does not move the 21, 200,
or 252 session windows. A company with no sector is standardised
against the whole universe.

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
flow, and net debt to EBITDA of at most 4. When EBITDA is not positive
the ratio is missing; the company still passes the debt ceiling if it
has net cash. A missing composite stays off the list. The shortlist is
the 60 highest composites.

## Open choices

- Group weights 40/30/30.
- The debt ceiling of 4.
- The shortlist of 60.
- Whether the books name factors that are not in this list. That is
  settled in M07, when each entry is cited or replaced.
