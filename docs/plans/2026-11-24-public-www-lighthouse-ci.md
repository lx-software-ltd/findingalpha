# Plan: Lighthouse CI for the public logo site

**Status**: Done
**Zone**: yellow (`apps/public_www/**`). `.github/workflows/lighthouse-public-www.yml` is not a `deploy-*.yml`.

## Goal

Audit the Vite logo site with `lx-software-ltd/actions/lighthouse-ci`, the same action `lx-software`, `siutindei`, and `evolvesprouts` call.

## Non-goals

- Do not add `@lhci/cli` as an npm dependency. The action runs `npx --yes @lhci/cli@0.15.1`.
- Do not make the job a required check. `main-protection` stays `lint`, `test`, and `security-summary`.
- Do not edit `.pre-commit-config.yaml`, deploy workflows, or the admin console.
- Do not copy locale paths, a staging bypass header, or a `production` environment. This build reads no site variables.
- Do not turn on `isSinglePageApplication`. CloudFront keeps real 403/404 responses, and the default collect URL is `/`.

## Files

- `apps/public_www/.lighthouserc.json` — collect `./dist`, assert the four category floors at 0.9
- `apps/public_www/src/lighthouse-config.test.ts` — locks that config
- `.github/workflows/lighthouse-public-www.yml` — build, then the shared action, then upload `.lighthouseci`
- `scripts/test_lighthouse_workflow.py` — pins, runner, and permissions
- `apps/public_www/README.md` and `docs/deployment/public-website.md` — how to run it
- `.gitignore` — ignore `.lighthouseci/`
- this plan

## Invariants this change preserves

- The public page stays one centred logo and no links.
- Workflow pins stay `48ffe6dadb6c1540b8992e8e8edfda4f8aa0933e # main 2026-11-24`, the pre-commit `rev`.
- Top-level workflow permissions stay `contents: read`. The job adds `statuses: write` only so Lighthouse can post a commit status.
- The job does not assume an AWS role and does not read production variables.

## Triggers

`lx-software` runs on a path-filtered pull request, Monday `15 6 * * 1`, and `workflow_dispatch`. `siutindei` and `evolvesprouts` are manual only because their builds need site variables. This build does not, so it follows the Vite sibling. The pull-request path filter is safe because the job is not a required check.

## Done when

- `npm test` and `npm run lint` pass in `apps/public_www`.
- `python3 -m unittest scripts/test_lighthouse_workflow.py` passes.
- `npx --yes @lhci/cli@0.15.1 autorun` against a local `dist/` meets the 0.9 floors.

## Rollback

Revert the pull request. The workflow, config, tests, gitignore line, and doc sections go with it. Nothing deployed changes.

## Open questions

`lx-software-ltd/actions` `docs/ci-contract.md` still says findingalpha has no Lighthouse run. That file is another repository. This pull request does not edit it.
