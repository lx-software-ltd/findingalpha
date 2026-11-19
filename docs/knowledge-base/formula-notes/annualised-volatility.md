# Annualised historic volatility

Sources: Inside Volatility Arbitrage-Javaheri.pdf, page 28, equation
1.4. Binomial Models in Finance.pdf, page 277. Vault-Guide to Advanced
Quant Interviews.pdf, page 62.

## Formula

R_n = ln(S_(n+1) / S_n)

R_bar = (1 / N) * sum over n of R_n

sigma_hist = sqrt( 252 / (N - 1) * sum over n of (R_n - R_bar)^2 )

That is: the sample standard deviation of daily log returns, times
sqrt(252).

## Symbols

- S_n: the daily closing price on day n.
- R_n: the daily log return.
- N: the number of observations.
- 252: business days in a year.

Javaheri and Binomial Models use 252. The Vault guide uses 250.

## Quote

Javaheri page 28: "we needed the factor 252, supposing that there are
approximately 252 business days in a year"

Binomial Models page 277: "annualized volatility) of 0.00123 × √252 =
0.195"
