# findingalpha

A private, single-owner system that looks for companies that are
structurally good investments, recommends once a day what to buy and
sell on a monthly to yearly horizon, and trades on paper money before
any real money.

Theory lives in a knowledge base. Every formula the code uses is written
in `contracts/methodology.json` with a citation. A language model reads,
argues, cites and proposes. It never computes a number that decides
money.

This repository is public. The owner's capital, holdings, personal data,
account identifiers and source PDFs never go into git.

## What is here

| Path | What it is |
| --- | --- |
| `apps/admin_web/` | The owner's dashboard. |
| `apps/public_www/` | The logo-only public site. |
| `backend/lambda/` | The engine, the sign-in trigger, and the API key authorizer. |
| `backend/infrastructure/` | The AWS CDK app. |
| `contracts/` | Shared constants, the methodology register, and the roadmap. |
| `brand/` | Favicons and the icon both sites share. |
| `docs/` | Architecture, deployment, the build plan, and research memos. |

The system is built one milestone at a time. The build plan is in
[`docs/plans/`](docs/plans/README.md). Start with
[`docs/plans/00-overview.md`](docs/plans/00-overview.md).
`contracts/roadmap.json` records how far each milestone is.

## Working here

Read [`AGENTS.md`](AGENTS.md) before changing anything. Zones, rules and
checks live there and in `.cursor/`. The zone map is
[`docs/architecture/zones.md`](docs/architecture/zones.md).

## Documentation

- [`docs/architecture/overview.md`](docs/architecture/overview.md): the
  rules that never bend and the shape of the system.
- [`docs/architecture/security.md`](docs/architecture/security.md): how
  the system enforces those rules.
- [`docs/deployment/setup.md`](docs/deployment/setup.md): one-time AWS
  and GitHub Actions setup.
- [`docs/deployment/admin-website.md`](docs/deployment/admin-website.md),
  [`docs/deployment/public-website.md`](docs/deployment/public-website.md),
  and [`docs/deployment/knowledge-base.md`](docs/deployment/knowledge-base.md):
  the runbooks.
- [`docs/plans/README.md`](docs/plans/README.md): the build plan, file
  by file.

## Security

To report a vulnerability, follow [`SECURITY.md`](SECURITY.md). Do not
open a public issue.

## Licence

Licensed under the Apache License, Version 2.0. The full text is in
[`LICENSE`](LICENSE).
