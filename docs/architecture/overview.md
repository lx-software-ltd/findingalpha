# Architecture

A private system for one owner. It scores US stocks from a written
register of formulas, asks language models to argue using a knowledge
base of the owner's papers, and places paper orders under hard limits.
The dashboard is at `admin.<domain>`.

## Rules that never bend

1. Theory lives in the knowledge base. Formulas and thresholds live in
   `contracts/methodology.json`. Code implements the register. A model
   never computes a number that decides money.
2. No order may leave gross exposure above 1.5 times equity. If prices
   fall through that level, the daily check sells down.
3. The system cannot withdraw, trade options, sell short, or change its
   own limits.
4. The broker code accepts only the paper host. `BrokerMode` allows only
   `paper` until a later, separate change.
5. A missing or unreadable kill switch means off.
6. A hold runs unless the owner says no. An approval runs only if the
   owner says yes. Paper orders are holds.
7. No model call runs inside an HTTP request. Long work is a job.
8. Model calls go through one client, with data collection denied, and
   count against a budget.
9. No secrets in git. Secret parameters use `noEcho`.
10. No personal data in git. Tests use `example.com`.
11. Shared constants live in `contracts/*.json` and are copied by
    `scripts/sync-contracts.py`.
12. Every order traces to a thesis with citations.
13. API keys store only a scrypt digest. No key can turn a switch on,
    reset a breaker, approve real money, or manage keys.

## Shape

Two stacks: `findingalpha` and `findingalpha-admin-web`.

`AdminApiFn` serves the dashboard and holds no broker or model secret.
`EngineFn` runs the jobs and holds those secrets. `PreTokenGenerationFn`
guards sign-in. A later milestone adds `PublicApiKeyAuthorizerFn`.

One DynamoDB table (`pk`, `sk`, index `gsi1`) and one KMS key. Prices
and filings are files in S3. The knowledge base bucket uses S3-managed
encryption so Bedrock needs no grant on the key.

Names are in `docs/plans/reference.md`.
