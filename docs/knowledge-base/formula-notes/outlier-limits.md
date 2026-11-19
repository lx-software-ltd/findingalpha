# Outlier limits

Source: Active Portfolio Management, Grinold & Kahn.pdf, page 255.

## Rule

Before a regression on stock characteristics, pull every outlier in to
3 standard deviations from the mean.

x_limited = min(max(x, mean(x) - 3 * sd(x)), mean(x) + 3 * sd(x))

The book states this in words. The formula above is written from it.

## Symbols

- x: one characteristic across stocks.
- sd: standard deviation.

## Quote

"One rule of thumb is to pull in all outliers in the Xn,k(t) to ±3
standard deviations about the mean."
