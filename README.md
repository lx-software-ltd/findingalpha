# Finding Alpha

A private, single-owner system that looks for companies that are
structurally good investments, recommends once a day what to buy and
sell on a monthly to yearly horizon, and trades on paper money before
any real money.

Theory lives in a knowledge base. Every formula the code uses is written
in [`contracts/methodology.json`](contracts/methodology.json) with a citation. A language model reads,
argues, cites and proposes. It never computes a number that decides
money.

This repository is public. The owner's capital, holdings, personal data,
account identifiers and source PDFs never go into git.

## What is here

| Path | What it is |
| --- | --- |
| [`apps/admin_web/`](apps/admin_web/) | The owner's dashboard. |
| [`apps/public_www/`](apps/public_www/) | The logo-only public site. |
| [`backend/lambda/`](backend/lambda/) | The engine, the sign-in trigger, and the API key authorizer. |
| [`backend/infrastructure/`](backend/infrastructure/) | The AWS CDK app. |
| [`contracts/`](contracts/) | Shared constants, the methodology register, and the roadmap. |
| [`brand/`](brand/) | Favicons and the icon both sites share. |
| [`docs/`](docs/) | Architecture, deployment, the build plan, and research memos. |

The system is built one milestone at a time. The build plan is in
[`docs/plans/`](docs/plans/README.md). Start with
[`docs/plans/00-overview.md`](docs/plans/00-overview.md).
[`contracts/roadmap.json`](contracts/roadmap.json) records how far each milestone is.

## Working here

Read [`AGENTS.md`](AGENTS.md) before changing anything. Zones, rules and
checks live there and in `.cursor/`. The zone map is
[`docs/architecture/zones.md`](docs/architecture/zones.md).

## Documentation

- [`docs/architecture/overview.md`](docs/architecture/overview.md): the
  rules that never bend and the shape of the system.
- [`docs/architecture/security.md`](docs/architecture/security.md): how
  the system enforces those rules.
- [`docs/architecture/zones.md`](docs/architecture/zones.md): which paths
  need a plan or an approval first.
- [`docs/deployment/setup.md`](docs/deployment/setup.md): one-time AWS
  and GitHub Actions setup.
- [`docs/deployment/admin-website.md`](docs/deployment/admin-website.md),
  [`docs/deployment/public-website.md`](docs/deployment/public-website.md),
  and [`docs/deployment/knowledge-base.md`](docs/deployment/knowledge-base.md):
  the runbooks.
- [`docs/plans/README.md`](docs/plans/README.md): the build plan, file
  by file. The numbered milestones run from
  [`00-overview.md`](docs/plans/00-overview.md) to
  [`11-safety-and-go-live-gate.md`](docs/plans/11-safety-and-go-live-gate.md).
  Lookups are in [`reference.md`](docs/plans/reference.md) and
  [`owner-checklist.md`](docs/plans/owner-checklist.md).
- [`docs/research/README.md`](docs/research/README.md): research memos,
  including [`data-sources.md`](docs/research/data-sources.md),
  [`managed-kb.md`](docs/research/managed-kb.md), and
  [`methodology-provisional.md`](docs/research/methodology-provisional.md).
- Formula notes in [`docs/knowledge-base/formula-notes/`](docs/knowledge-base/formula-notes/):
  [`annualised-volatility.md`](docs/knowledge-base/formula-notes/annualised-volatility.md),
  [`earnings-yield.md`](docs/knowledge-base/formula-notes/earnings-yield.md),
  [`enterprise-value.md`](docs/knowledge-base/formula-notes/enterprise-value.md),
  [`free-cash-flow.md`](docs/knowledge-base/formula-notes/free-cash-flow.md),
  [`industry-neutral.md`](docs/knowledge-base/formula-notes/industry-neutral.md),
  [`interest-coverage.md`](docs/knowledge-base/formula-notes/interest-coverage.md),
  [`momentum.md`](docs/knowledge-base/formula-notes/momentum.md),
  [`moving-average.md`](docs/knowledge-base/formula-notes/moving-average.md),
  [`outlier-limits.md`](docs/knowledge-base/formula-notes/outlier-limits.md),
  [`roic.md`](docs/knowledge-base/formula-notes/roic.md),
  and [`standardised-score.md`](docs/knowledge-base/formula-notes/standardised-score.md).

## Security

To report a vulnerability, follow [`SECURITY.md`](SECURITY.md). Do not
open a public issue.

## Licence

Licensed under the Apache License, Version 2.0. The full text is in
[`LICENSE`](LICENSE).
