# Standardised score

Source: Active Portfolio Management, Grinold & Kahn.pdf, page 16.

## Formula

score = (x - mean(x)) / standard_deviation(x)

The score has zero mean and unit standard deviation across the stocks
scored. The book turns a score into a forecast of residual return:

alpha = residual_volatility * IC * score

The book states this in words. The formula above is written from it.

## Symbols

- x: the raw signal for one stock.
- IC: the information coefficient, the correlation between scores and
  later returns.
- residual_volatility: the stock's residual risk.

## Quote

"Alpha = volatility · IC · score, which allows us to relate a
standardized (zero mean and unit standard deviation) score"
