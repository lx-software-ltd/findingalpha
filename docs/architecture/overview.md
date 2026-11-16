# Architecture

findingalpha is one owner's research and paper-trading system. Theory
lives in a knowledge base. Every formula the code uses is written in
`contracts/methodology.json` with a citation. A language model reads,
argues, cites and proposes. It never computes a number that decides money.

## Rules that never bend

1. **Three layers.** The knowledge base holds the theory. The contract
   holds the register. Code implements the register and is unit-tested.
2. **Leverage cap in code.** No order may leave gross exposure above
   1.5 times equity. If prices push exposure above the target, the daily
   check sells down.
3. **Never available to the system:** withdrawals, options, short
   selling, changing its own limits.
4. **Paper only until the gate.** Broker code refuses any host other
   than the paper host. `BrokerMode` allows only `paper`.
5. **Kill switches fail closed.** A missing or unreadable switch means off.
6. **Holds and approvals are different.** A hold runs unless the owner
   says no. An approval runs only if the owner says yes. Paper orders
   are holds.
7. **No model call inside an HTTP request.** Long work is a job with a
   DynamoDB row. The page polls.
8. **Every model call goes through one client** with data collection
   denied, and is counted against a daily budget.
9. **No secrets in git.** Secret stack parameters use `noEcho: true`.
   Keys live in Secrets Manager.
10. **No personal data in git.** Tests use invented people and
    `example.com`. The capital amount and holdings never appear here.
11. **Shared constants live in `contracts/*.json`** and are synced with
    `python3 scripts/sync-contracts.py`.
12. **Every order traces to a thesis record with citations.**
13. **API keys are limited.** Only a scrypt digest is stored. A key has
    a tier, scopes and an expiry. No key can turn a switch on, reset a
    breaker, approve an order or manage keys.

## Shape

```
                 owner
        +----------+-----------+
        | browser              | email 13:30 HKT
        v                      ^
 CloudFront + S3 (SPA)         |
 admin.<domain>                |
        |  Cognito ID token    |
        v                      |
 API Gateway HTTP API          |
        |                      |
        v                      |
 AdminApiFn (reads, vetoes) ---+-----------------+
        |                                        |
        v                                        |
 DynamoDB single table  <----  EngineFn (jobs) --+--> SES
 S3 data bucket         <----     ^   |  |  |
                                  |   |  |  +--> Alpaca paper API
        EventBridge Scheduler ----+   |  +-----> OpenRouter
                                      +--------> Bedrock Managed KB
                                      +--------> SEC EDGAR, Alpaca data
 S3 KB bucket (owner PDFs) ---> Bedrock Managed KB
```

Two stacks: `findingalpha` (everything except web hosting) and
`findingalpha-admin-web` (S3 and CloudFront). Two Lambda functions share
`backend/lambda/engine`. `AdminApiFn` serves the dashboard and holds no
broker or model keys. `EngineFn` runs jobs and holds those keys.
`PreTokenGenerationFn` guards sign-in. One DynamoDB table uses `pk` /
`sk` and the index `gsi1`. One KMS key encrypts Lambda environment
variables, logs, DynamoDB and the dead-letter queue.

Names are in [`../plans/reference.md`](../plans/reference.md).
