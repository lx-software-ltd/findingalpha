# Plan: Shared actions repository and CI convergence

**Status**: Draft
**Zone**: red

This is a hand-off plan. An agent can execute it across five
repositories of the `lx-software-ltd` organisation: `findingalpha`,
`lx-software`, `evolvesprouts`, `siutindei`, and a new `actions`.

The owner approved the direction in chat on 20 Nov 2026. That approval
covers the design in this file. It does not cover writes to red paths.
Each of those waits at an approval gate listed under
[Approval gates](#approval-gates).

Facts marked "measured" come from these commits. Measure again if
`main` has moved.

| Repository | Commit read |
| --- | --- |
| `findingalpha` | `2cbc059` |
| `lx-software` | `186d7fb` |
| `evolvesprouts` | `c1d4686` |
| `siutindei` | `87b1915` |

## Goal

1. One public repository, `lx-software-ltd/actions`, holds every CI and
   deploy building block that more than one repository uses. The blocks
   are composite actions. The harness scripts are also published from
   it as pre-commit hooks.
2. The four product repositories call those actions and delete their
   own copies.
3. The four repositories' workflows do the same thing: the same checks,
   the same tool versions, the same failure behaviour, the same job
   names. A remaining difference is either a declared input (app
   directories, stack names, parameters) or is listed under
   [Differences that stay](#differences-that-stay).
4. A check in each repository fails when its workflows drift from the
   shared shape.

## Non-goals

- No reusable workflows (`workflow_call`). They rename check runs to
  `caller / job`, and the organisation ruleset requires checks named
  exactly `lint` and `test`.
- No change to what is deployed. Stacks, parameters, and the hosting
  model stay. `findingalpha` and `lx-software` keep S3 and CloudFront.
  `evolvesprouts` and `siutindei` keep Amplify.
- No change by the agent to organisation rulesets, IAM, secrets, or
  repository settings. Those are [owner tasks](#owner-tasks).
- Triggers stay per repository. That includes `repository_dispatch`
  and the `board-*` workflows in `siutindei`.
- `ai-cxo` is not onboarded. It has no workflows yet.

## Decisions

"Approved" means the owner accepted it in chat. "Defaulted" means the
plan author chose it because the owner left it open. The owner can
overrule a defaulted row before work starts.

| # | Decision | Source |
| --- | --- | --- |
| D1 | Composite actions, not reusable workflows | Approved |
| D2 | A public repository `lx-software-ltd/actions` | Approved |
| D3 | Callers pin by full commit SHA with a version comment. Each repository's weekly Dependabot `github-actions` group bumps the pin | Approved |
| D4 | Secret-free CI pieces first, deploy pieces last. `findingalpha` is the pilot for every step | Approved |
| D5 | Pre-commit hooks are published from `actions` | Approved |
| D6 | Apache-2.0 licence, as in the other five repositories | Defaulted |
| D7 | The AWS role trust is narrowed from the organisation wildcard to the named repositories. `actions` is not in the list | Defaulted |
| D8 | The account id is read as `secrets.AWS_ACCOUNT_ID \|\| vars.AWS_ACCOUNT_ID` and masked in every repository, as `findingalpha` does today | Defaulted |
| D9 | When repositories differ, the target is the strictest variant in use today, unless the [convergence register](#convergence-register) says otherwise | Defaulted |
| D10 | An action implements the target behaviour from its first version. A repository that is not there yet passes an explicit input. Convergence is deleting that input | Defaulted |

## Current state

Measured.

- 66 workflow files, about 10,400 lines, 134 jobs. `findingalpha` has
  10 files, `lx-software` 14, `evolvesprouts` 20, `siutindei` 22.
- No repository has `.github/actions` or a `workflow_call` workflow.
- The repositories form two pairs. This plan calls them pair A and
  pair B.
  - **Pair A** is `findingalpha` and `lx-software`. Web apps on S3 and
    CloudFront. Actions pinned by tag. Runner `ubuntu-26.04`.
  - **Pair B** is `evolvesprouts` and `siutindei`. Amplify, Flutter,
    Postgres-backed tests. Actions pinned by SHA.
- Inside a pair, whole files are close. `security.yml` is 98% the same
  in pair A, `amplify-promote.yml` 97% in pair B. Across pairs, most
  whole files match 17% to 55%, but single steps match. That is why
  the unit of sharing is a step-level action.
- `scripts/check_pii.py` and `scripts/check-pii.sh` are byte-identical
  in all four. `verify_github_rulesets.py` has two variants.
  `validate_agent_rules.py` has four, which differ mostly in their
  required-file lists.
- All five existing repositories are public.

## Live problems

Found during the inventory. Stage 1 fixes the ones an agent can fix.

1. **Pair B has no `lint` or `test` job.** The organisation ruleset
   `main-protection` (created 20 Nov 2026, 16:40 Hong Kong time)
   requires status checks named `test` and `lint` on the default
   branch of every repository. Pair B's `lint.yml` and `test.yml` have
   neither job, and both filter `pull_request` by path. Unless the
   ruleset has a bypass the agent's token cannot see, the next pull
   request to `main` in either repository waits on checks that nothing
   reports. Not observed yet: no pull request has merged in pair B
   since the ruleset was created.
2. **`verify-rulesets` fails every week** in `lx-software`,
   `evolvesprouts`, and `siutindei` (runs of 9 and 16 Nov). On 16 Nov
   `lx-software` and `siutindei` failed because the repository ruleset
   was disabled. That ruleset is gone and the organisation ruleset is
   active. Pair B's script treats fewer than one approving review as
   an error, and the organisation ruleset asks for zero. Reading the
   code, pair B will keep failing on 23 Nov. `findingalpha` has no
   recorded run.
3. **`ai-cxo` has no workflows** and is under the same ruleset. Out of
   scope. The owner should know.
4. **The new `actions` repository inherits both organisation
   rulesets.** It needs `lint` and `test` jobs from its first pull
   request, and nobody without a bypass can create a `v*` tag in it.
5. **`lx-software/docs/architecture/github-actions-trust-policy.json`
   prints the AWS account id** in a public repository.
6. **`lint.yml`, `test.yml`, and `check-lockfiles.yml` have no
   `permissions` block** in any of the four. Neither has
   `e2e-admin-web.yml` in `siutindei`. Those jobs run with the
   repository's default token permissions.
7. **`role-session-name` is missing** on 2 of 5 credential steps in
   `findingalpha` and 1 of 6 in `lx-software`.

## Owner tasks

Only the owner can do these. Stage 2 needs O1 to O3. The others block
the stage named in the last column.

| # | Task | Blocks |
| --- | --- | --- |
| O1 | Create the public repository `lx-software-ltd/actions` with an initial commit (README and the Apache-2.0 licence). Give the executing agent write access to it and to the four product repositories | Stage 2 |
| O2 | Confirm the organisation's Actions policy lets workflows use actions from `lx-software-ltd/*`. The agent's token gets a 403 on that setting | Stage 2 |
| O3 | Decide how `v*` tags get created in `actions`: the owner tags each release, or a named actor gets a bypass on the `release-tags` ruleset for that repository | Stage 2, soft |
| O4 | Say whether `main-protection` has a bypass list, and whether zero approving reviews is intended | Stage 1 |
| O5 | Narrow the `GitHubActionsRole` trust to the four named repositories (D7). Replace the account id in the `lx-software` trust-policy document with a placeholder | Stage 5 |
| O6 | Add `AWS_ACCOUNT_ID` as a secret where it is only a variable today (D8). Optional: the variable keeps working | Stage 5 |
| O7 | Run each deploy workflow by hand after its pull request merges. The agent's `gh` is read-only and it must not trigger deploys | Stages 5, 6 |

About O3. Tags are not on the critical path. Until tags exist, callers
pin the SHA with the comment `# main <yyyy-mm-dd>` and the agent bumps
pins by hand in one pull request per repository. Do not pick a tag
pattern that avoids the `refs/tags/v*` rule.

## The `actions` repository

### Layout

```text
actions/
  <action-name>/action.yml      one top-level directory per action
  <action-name>/README.md       inputs, outputs, permissions, example
  <action-name>/*.py|*.sh       payload scripts for that action
  lib/                          payload shared by several actions
  hooks/                        entry scripts for pre-commit
  .pre-commit-hooks.yaml
  fixtures/                     sample trees the self-tests run on
  tests/test_*.py               unittest
  docs/ci-contract.md           the shared workflow shape (see below)
  docs/plans/                   this plan, then per-step plans
  .github/workflows/            lint.yml, test.yml, security.yml
  .github/dependabot.yml
  AGENTS.md, docs/architecture/zones.md, .github/PULL_REQUEST_TEMPLATE.md
```

### Rules for every action

- `runs.using: composite`. Every `run` step names its `shell`.
- An action cannot read `secrets` or `vars`. The caller passes them as
  inputs. Mask a sensitive input with `::add-mask::` before any other
  use, and never echo it.
- Inputs reach scripts through `env:`. Do not write
  `${{ inputs.x }}` inside a `run:` block. That is script injection.
- Payload is addressed as `"$GITHUB_ACTION_PATH/file"`, and shared
  payload as `"$GITHUB_ACTION_PATH/../lib/file"`. Use the environment
  variable, not the `github.action_path` expression, so the path is
  right inside a job container.
- An action does not call another action in this repository.
  `uses: ./x` resolves to the caller's checkout, and the full form
  needs a SHA that does not exist yet. Share code through `lib/`.
- Third-party actions used inside a composite are pinned by full SHA
  with a version comment.
- Python payload uses the standard library only and runs on
  Python 3.12. Tests use `unittest` in `tests/test_*.py`.
- A composite action cannot set `permissions` or a job `container`.
  Each README states what the calling job must grant.
- The repository is public. No secret, account id, internal hostname,
  or personal data goes in it. Its own `pii-denylist` and `gitleaks`
  jobs run on every pull request.
- No workflow in `actions` requests `id-token: write` or calls AWS.
  Actions that touch AWS are tested only in the product repositories.

### Self-test

`actions/.github/workflows/test.yml` runs the unit tests, then runs
each secret-free action with `uses: ./<action-name>` against
`fixtures/`. Inside this repository `./` is the right path. Each
action has at least one passing fixture and one fixture that must
fail. The job `test` is a gate built with `require-jobs`. `lint.yml`
has a `lint` gate the same way.

### Releases and pins

- Versions are `vMAJOR.MINOR.PATCH`. A breaking change to an input is
  a major version. Tags never move.
- Callers write
  `uses: lx-software-ltd/actions/<action-name>@<40-hex> # vX.Y.Z`.
- Each product repository's Dependabot `github-actions` entry already
  groups all action updates weekly. `actions` gets its own
  `github-actions` entry that covers the action subdirectories.
- Pre-commit `rev:` in a product repository equals the SHA its
  workflows pin. The conformance check enforces that.

### CI contract

`docs/ci-contract.md` in `actions` is the written form of "they do the
same thing". It lists the workflow files every repository has, the job
ids in each, which job is the gate, the triggers that are fixed and
the ones that are free, and the allowed runner labels. The
`workflow-conformance` action checks a repository against it. Draft
it from the [target shape](#target-workflow-shape) below.

## Action catalog

"Source" is the copy to start from. "Callers" are the repositories
that end up using it.

### Gates and harness

| Action | What it does | Main inputs | Source | Callers |
| --- | --- | --- | --- | --- |
| `require-jobs` | Fails unless every job in `needs` succeeded. Writes a result table to the step summary | `needs-json`, `allow-skipped` (default `false`) | `findingalpha` `lint.yml`, job `lint` | All four, in `lint`, `test`, `security-summary` |
| `agent-harness` | Runs the harness validators on the caller's checkout: agent rules, file length, test focus | `config` (default `.github/harness.json`) | `findingalpha` scripts, with the per-repository lists moved to the config file | All four |
| `workflow-conformance` | Checks workflows against the CI contract: SHA pins, runner labels, top-level `permissions`, gate jobs, no `pull_request` path filter on a gated workflow, pre-commit `rev` equals the pinned SHA | `mode` (`warn` or `enforce`) | New | All four and `actions` |
| `pii-denylist` | Runs `check_pii.py` from the action against the caller's hash list | `denylist-path` (default `scripts/pii-denylist.sha256`) | Any (identical) | All four |
| `verify-rulesets` | Checks that the rules on `main` require the gate jobs this repository defines | `token`, `required-checks` (default `lint test`) | `findingalpha` | All four |

### Security scanning

| Action | What it does | Main inputs | Source | Callers |
| --- | --- | --- | --- | --- |
| `gitleaks` | Downloads the pinned Gitleaks with checksum and retry, then scans | `config-path` | `findingalpha` | All four |
| `checkov-cloudformation` | Runs Checkov on a synthesised template directory, drops findings suppressed in source, uploads SARIF without failing on upload errors | `directory`, `skip-if-missing` | `findingalpha` | All four |
| `codeql` | `init` then `analyze` for one interpreted language, with a fixed category | `language`, `config-file` | `evolvesprouts` | All four |
| `semgrep` | `semgrep scan` with rule packs, an empty-SARIF fallback, the suppression filter, and upload with category `semgrep`. Steps use `shell: sh` because the calling job runs in the Semgrep container | `rules`, `exclude-rules` | `siutindei` `semgrep.yml` | All four |
| `pip-audit` | Audits requirements files | `requirements`, `ignore-vulns` | `siutindei` | All four |
| `bandit` | Runs Bandit | `paths`, `skip` | `siutindei` | All four |
| `npm-audit` | `npm audit` with a retry on registry 503 | `directories`, `audit-level` (default `high`), `omit` (default `dev`) | `evolvesprouts` `lint.yml` | All four |

The SARIF suppression filter lives in `lib/` and is used by
`checkov-cloudformation` and `semgrep`.

### Setup and lockfiles

| Action | What it does | Main inputs | Source | Callers |
| --- | --- | --- | --- | --- |
| `setup-node` | `actions/setup-node` with the npm cache, then `npm ci`. The default Node version for the organisation is set here | `working-directory`, `node-version`, `install` | `findingalpha` | All four |
| `setup-python` | `actions/setup-python` with the pip cache. Default 3.12 | `python-version`, `requirements` | `findingalpha` | All four |
| `node-lockfiles` | Fails when `npm ci` or the lockfile drifts in any listed directory | `directories` | `findingalpha` | All four |
| `python-requirements-pins` | Fails on an unpinned requirement, following `-r` includes | `files` | `siutindei` | All four |
| `flutter-lockfiles`, `pod-lockfiles` | Lockfile drift for Flutter and CocoaPods | `working-directory`, `flutter-version` | `siutindei` | Pair B |
| `playwright-install` | Installs browsers, with the apt fallback | `working-directory`, `browsers` | `siutindei` `test.yml` | `findingalpha`, `lx-software`, `siutindei` |

### AWS and deploy

These need credentials, so they are proven in a product repository,
never in `actions`.

| Action | What it does | Main inputs | Source | Callers |
| --- | --- | --- | --- | --- |
| `aws-oidc` | Checks the account id and region are set, masks the account id, assumes `GitHubActionsRole` with a session name. Output `ready` | `account-id`, `region`, `role-name`, `required` | `findingalpha` `cdk-diff.yml` and `deploy-backend.yml` | All four, 29 call sites |
| `cdk-bootstrap-check` | Reads the bootstrap version from SSM and fails with a hint when it is missing | `qualifier` | `findingalpha` | All four |
| `cfn-stack-outputs` | Reads named stack outputs into step outputs | `stack`, `outputs` | `findingalpha` `deploy-admin-web.yml` | All four |
| `cdk-diff` | Runs `cdk diff`, removes the account id, writes the step summary | `working-directory`, `stacks`, `args` | `findingalpha` | All four |
| `s3-cloudfront-deploy` | Syncs a build to S3 and invalidates CloudFront | `bucket`, `distribution-id`, `source` | `findingalpha` `scripts/deploy/` | Pair A |
| `amplify-release` | Starts an Amplify job and waits for it, and promotes a release | `app-id`, `branch`, `mode` | `evolvesprouts` | Pair B |
| `lighthouse-ci` | Runs Lighthouse CI on a built site and uploads the report | `working-directory`, `urls`, `budget` | `lx-software` | `lx-software`, pair B |
| `cdk-deploy` | Deploys stacks with parameters from a file, retries, and recovers from `UPDATE_ROLLBACK_FAILED` | `stacks`, `parameters-file`, `attempts` | `siutindei` `deploy-backend.yml` | All four |

### Leftover duplication

After the catalog is in use, pair B's mobile and promote workflows
(`deploy-ios.yml`, `deploy-mobile.yml`, `promote-public-www.yml`,
`smoke-public-www-staging.yml`) still share code. The rule for those:
extract a block when it is ten lines or more and is the same in both
repositories after project names are replaced with inputs. Do not
extract a wrapper around a single `uses:`.

## Convergence register

Each row is one difference and its target. "Changes" names the
repositories whose behaviour changes. A row is done when no caller
passes the input that kept the old behaviour.

| # | Topic | Today (measured) | Target | Changes |
| --- | --- | --- | --- | --- |
| C01 | Action pins | Tags in pair A, SHAs in pair B | Full SHA with a version comment | Pair A |
| C02 | Linux runner | `ubuntu-26.04` in pair A, `ubuntu-24.04` in `evolvesprouts`, `ubuntu-latest` in `siutindei` | `ubuntu-26.04` | Pair B |
| C03 | macOS runner | `macos-latest` in pair B | One pinned label | Pair B |
| C04 | Node version | `lts/*` in pair A and parts of pair B, `22.22.2` in two `evolvesprouts` workflows, `24` in `siutindei` | One default, set in `setup-node`. Callers pass their current value until the owner picks | All four |
| C05 | Python version | 3.12 everywhere, except 3.13 in three `siutindei` jobs. `siutindei`'s Lambdas run 3.12 | 3.12 | `siutindei` |
| C06 | Flutter version | Floats on `stable` in `evolvesprouts`, pinned in `siutindei` | Pinned, a required input | `evolvesprouts` |
| C07 | Merge gates | Pair A has gate jobs `lint` and `test` and no `pull_request` path filter. Pair B has neither | Gate jobs in all four, no `pull_request` path filter on `lint.yml` and `test.yml` | Pair B |
| C08 | Token permissions | No `permissions` block on `lint.yml`, `test.yml`, `check-lockfiles.yml` | `permissions: contents: read` at the top of every workflow, more only per job | All four |
| C09 | Checkout ref | `evolvesprouts` checks out the pull request head SHA. The others use the default merge ref | The default merge ref, unless the `evolvesprouts` history shows a reason to keep the head SHA | `evolvesprouts` |
| C10 | Gitleaks | Same version and checksum. Retry only in pair A | Retry everywhere | Pair B |
| C11 | Checkov | Two pins. `siutindei` uploads unfiltered SARIF | One pin, findings suppressed in source filtered out, upload errors do not fail the job | `siutindei`, pin in all |
| C12 | CodeQL | `javascript` and `python` in pair A. `python` and `javascript-typescript` with a config file in `evolvesprouts`. `python` only in `siutindei` | `python` and `javascript-typescript` in all four | Pair A, `siutindei` |
| C13 | Semgrep | A job in `security.yml` running `semgrep ci` in pair A and `evolvesprouts`. A dedicated `semgrep.yml` running `semgrep scan` in `siutindei` | Dedicated `semgrep.yml`, job `semgrep/ci`, `semgrep scan`, packs `p/python p/javascript p/security-audit p/secrets p/owasp-top-ten` | Pair A, `evolvesprouts` |
| C14 | Semgrep image | `semgrep/semgrep` with no tag or digest in all four | Pinned by digest | All four |
| C15 | Python dependency audit | `pip-audit` and Bandit only in pair B | Both in all four | Pair A |
| C16 | npm audit | Only in `evolvesprouts`, inside `lint.yml` | Job `npm-audit` in `security.yml` in all four | All four |
| C17 | PII check in CI | A `pii-denylist` job in `security.yml` in pair A and `siutindei` (and again in its `test.yml`). `evolvesprouts` runs it only through pre-commit | One `pii-denylist` job in `security.yml` in all four | Pair B |
| C18 | Lockfile checks | Node only in pair A. Flutter, Node, iOS, and Python requirements in pair B, with two requirements checkers | Node and Python requirements in all four. Flutter and iOS in pair B | All four |
| C19 | Rulesets check | Pair A matches required checks exactly and warns on review count. Pair B matches by substring and fails below one review | Pair A's behaviour | Pair B |
| C20 | Harness validators | Four variants of `validate_agent_rules.py`, two each of the file-length and test-focus checks | One implementation, configured by `.github/harness.json` | All four |
| C21 | Pre-commit | `repo: local` hooks that run each repository's own script copies | Hooks from `actions` at the SHA the workflows pin | All four |
| C22 | Security summary | Hand-written per repository | `require-jobs` over `needs` | All four |
| C23 | AWS credentials | Session name missing on three steps. Account id is a plain variable outside `findingalpha` | `aws-oidc` everywhere (D8) | All four |
| C24 | CDK bootstrap | Pair A checks the bootstrap version and stops. Pair B runs `cdk bootstrap` on every deploy | Check only. Bootstrapping is the manual `cdk-bootstrap.yml`, which `findingalpha` gains | Pair B, `findingalpha` |
| C25 | CDK diff | Runs on pull requests with a masked summary in `findingalpha`. Manual in the other three | Runs on pull requests that touch infrastructure paths, masked summary | `lx-software`, pair B |
| C26 | Backend deploy | Pair A deploys once with a parameter script. Pair B retries three times, detects errors that cannot be retried, and recovers a failed rollback | One `cdk-deploy` with pair B's recovery and a per-repository parameters file | All four |
| C27 | Playwright install | The apt fallback only in `siutindei` | The fallback wherever Playwright runs | Pair A |
| C28 | Dependabot | A 7-day cooldown only in pair B | The cooldown in all four, with `lx-software-ltd/actions` excluded from it | All four |

Notes on rows that carry risk:

- **C07** removes path filters, so pair B runs Flutter and Postgres
  jobs on every pull request. Record CI minutes before and after. If
  the cost matters, add a `changes` job and pass
  `allow-skipped: true`. That is safe only when the gate lists every
  job in `needs`.
- **C12** renames CodeQL categories. Old alerts under the old category
  stay open until they are dismissed by hand. `siutindei` gets
  JavaScript findings for the first time.
- **C13** exists because GitHub's code-scanning setup for Semgrep looks
  for a file named `semgrep.yml`. Rule exclusions start as a
  per-repository input and each carries its reason in a comment.
- **C15** and **C16** add checks to repositories that never ran them.
  Run them first, fix or record each finding with a reason, then turn
  the job on.
- **C24**, **C25**, and **C26** change deploy behaviour. Each has its
  own gate.

## Target workflow shape

Every product repository ends with these files and job ids. A
repository adds its own stack jobs under `lint.yml` and `test.yml`.

| File | Jobs | Notes |
| --- | --- | --- |
| `lint.yml` | Per-stack lint jobs, `validate-agent-harness`, `workflow-conformance`, gate `lint` | No `pull_request` path filter |
| `test.yml` | Per-stack test jobs, gate `test` | No `pull_request` path filter |
| `security.yml` | `checkov`, `codeql`, `pii-denylist`, `secrets-scan`, `dependency-audit`, `bandit`, `npm-audit`, `security-summary` | Push, pull request, weekly |
| `semgrep.yml` | `semgrep/ci` | Skips Dependabot |
| `check-lockfiles.yml` | `node-lockfiles`, `python-requirements`, and in pair B `flutter-lockfiles`, `ios-lockfiles` | |
| `verify-rulesets.yml` | `verify-branch-protection` | Weekly, Monday |
| `cdk-diff.yml` | `diff` | Pull requests on infrastructure paths |
| `cdk-bootstrap.yml` | `bootstrap` | Manual only |
| `deploy-backend.yml` | `deploy` | `environment: production`, `main` only |
| Web deploy workflows | Per repository | Per hosting model |

## Differences that stay

- Hosting: S3 and CloudFront in pair A, Amplify in pair B.
- Mobile workflows exist only in pair B.
- Extra triggers: `repository_dispatch`, `board-*`, Figma sync, key
  management, the legacy import, the apex redirect probe.
- Stack names, parameters, app directories, and rule exclusions. They
  are inputs.
- `findingalpha` has no Lighthouse run. Its public site is a logo
  page.

## Approval gates

A red step needs the owner to say go in chat, to the agent doing the
work, naming the gate. Approving this plan is not approving a gate.

| Gate | Covers | Red in |
| --- | --- | --- |
| G1 | `verify-rulesets.yml` and the rulesets script | `lx-software`, `evolvesprouts`, `siutindei` |
| G2 | The PII script trio, `.pre-commit-config.yaml`, and `.cursor/hooks*` where a hook calls a moved script | All four for the PII trio. `findingalpha`, `lx-software`, `siutindei` for pre-commit |
| G3 | Credential and read-only AWS steps inside `deploy-*.yml` and `promote-*.yml`: `aws-oidc`, `cdk-bootstrap-check`, `cfn-stack-outputs`. Also C24 | All four |
| G4 | Web deploy actions: `s3-cloudfront-deploy`, `amplify-release`. Includes `scripts/deploy/**` | All four |
| G5 | `cdk-deploy` (C26). Needs its own design note first | All four |

Workflows that no zone map lists (`lint.yml`, `test.yml`,
`security.yml`, `check-lockfiles.yml`, `cdk-diff.yml`) are treated as
yellow. `siutindei`'s board policy refuses `.github/**` to board
agents, so this work is done there by a normal agent session.

## Steps

Do the stages in order. Inside a stage, do the steps in order unless
one says otherwise. Every step that changes a product repository
follows the [rollout procedure](#rollout-procedure).

### Stage 1. Repairs that need no new repository

- **SA-101** Add gate jobs to pair B. In `evolvesprouts` and
  `siutindei`, add a job `lint` to `lint.yml` and a job `test` to
  `test.yml`. Each has `if: always()`, `needs` every other job in the
  file, and fails unless all succeeded. Copy the step from
  `findingalpha` `lint.yml`. Remove `paths` from `pull_request` in
  both files and keep it on `push`. Yellow. Evidence: the pull request
  itself shows check runs named `lint` and `test`.
- **SA-102** Add `permissions: contents: read` to `lint.yml`,
  `test.yml`, and `check-lockfiles.yml` in all four, and to
  `e2e-admin-web.yml` in `siutindei`. Grant more per job only where a
  job fails without it. Yellow.
- **SA-103** Report to the owner what the next `verify-rulesets` run
  does in each repository. Do not edit it here. SA-304 replaces it.

### Stage 2. Create `actions` and prove the path

Needs O1 and O2.

- **SA-201** Scaffold `actions`: layout, `AGENTS.md`, zone map, pull
  request template, Dependabot for `github-actions`, `lint.yml` and
  `test.yml` with gate jobs,
  `security.yml` with `pii-denylist`, `secrets-scan`, and `codeql`.
  Copy this plan to `actions/docs/plans/` and track progress there.
  The gate jobs use an inline step in this one pull request.
- **SA-202** Add `require-jobs` with unit tests and two fixtures.
  Switch the repository's own gates to `uses: ./require-jobs`.
  Release `v0.1.0`, or record the SHA if tags are not available yet.
- **SA-203** Pilot in `findingalpha`. Replace the inline gate step in
  `lint.yml` and `test.yml` with `require-jobs`. Evidence: check-run
  names are the same before and after, and both gates pass.
- **SA-204** Check the update path. After the next release of
  `actions`, confirm Dependabot opens a pull request in `findingalpha`
  that moves the SHA and the version comment. If it does not, record
  why and use manual bumps.
- **SA-205** Roll `require-jobs` out to `lx-software`,
  `evolvesprouts`, and `siutindei`.

### Stage 3. Secret-free CI actions

For each step: build the action in `actions` with tests and fixtures,
release, pilot in `findingalpha`, then roll out to the other three.
A repository that differs from the target passes an input that keeps
its current behaviour. Extraction and behaviour change never share a
pull request.

- **SA-301** `setup-node` and `setup-python`. Callers pass their
  current versions.
- **SA-302** `pii-denylist`. The workflow file is yellow, but this
  swaps the red PII script for the shared one in CI, so it waits for
  gate G2. The local `scripts/check_pii.py` and `scripts/check-pii.sh`
  stay until SA-307, when pre-commit stops calling them.
- **SA-303** `gitleaks`, `checkov-cloudformation`, `codeql`,
  `semgrep`. The caller keeps its own synth step for Checkov.
  Evidence: the same finding count before and after for each tool.
- **SA-304** `verify-rulesets`. Red in three repositories, gate G1.
  Move `test_verify_github_rulesets.py` to `actions`. This step is
  the one exception to "no behaviour change in an extraction": pair B
  takes pair A's behaviour here (C19), because pair B's current check
  fails against the live ruleset.
- **SA-305** `node-lockfiles`, `python-requirements-pins`,
  `flutter-lockfiles`, `pod-lockfiles`.
- **SA-306** `agent-harness`. Write `.github/harness.json` in each
  repository from the constants in its current scripts: required
  rules and skills, size limits, scan roots, skip patterns, allowlist
  path. Evidence: the old script and the new action report the same
  result on `main`, and the same failure on a fixture that breaks a
  rule.
- **SA-307** Pre-commit hooks. Add `.pre-commit-hooks.yaml` to
  `actions` with `language: script` entries for `check-pii`,
  `validate-agent-rules`, `check-file-length`, and `check-test-focus`.
  Each entry script finds the repository root from the working
  directory. Point each repository's `.pre-commit-config.yaml` at
  `actions`, then delete the local script copies and their tests.
  Update anything that names the old paths: `.cursor/hooks/**`, the
  `verify-change` skill, `AGENTS.md`, the zone map. Red, gate G2.
- **SA-308** `pip-audit`, `bandit`, `npm-audit`, `playwright-install`.
  In this stage only the repositories that already run them call
  them.
- **SA-309** `workflow-conformance` in `warn` mode in all four and in
  `actions`. Write `docs/ci-contract.md`.

### Stage 4. Converge CI

One register row per pull request per repository. Suggested order:
C01, C02, C10, C11, C05, C06, C28, then C13 and C14, C12, C17, C18,
C22, C15, C16, C27, C03, C04, C09. C04 waits for the owner's Node
choice. When a repository has no row left, switch its
`workflow-conformance` to `enforce`.

Rows closed by other steps: C07 by SA-101, C08 by SA-102, C19 by
SA-304, C20 by SA-306, C21 by SA-307, C23 to C25 by SA-504, C26 by
SA-603.

### Stage 5. Credentials and read-only AWS

Needs O5 for the trust change. `findingalpha` `cdk-diff.yml` is the
canary, because it runs on pull requests and deploys nothing.

- **SA-501** `aws-oidc` in `findingalpha` `cdk-diff.yml`. Move the
  matching assertions from `scripts/test_workflow_secrets.py`: the
  masking and missing-setting assertions become action tests in
  `actions`, and the `findingalpha` test asserts that the workflow
  calls the action at a 40-character SHA and passes
  `secrets.AWS_ACCOUNT_ID || vars.AWS_ACCOUNT_ID`. Tests first.
- **SA-502** `cdk-bootstrap-check` and `cdk-diff` in `findingalpha`,
  then the other three with their current triggers.
- **SA-503** `aws-oidc` and `cfn-stack-outputs` in the deploy and
  promote workflows. Red, gate G3. One repository at a time,
  `findingalpha` first. After each merge the owner runs the workflow
  (O7). Do not start the next repository until that run is green.
- **SA-504** C23, C24, C25. C24 is part of gate G3 and is confirmed
  again by name, because it removes `cdk bootstrap` from pair B's
  deploys.

### Stage 6. Deploy actions

- **SA-601** `s3-cloudfront-deploy` in pair A and `amplify-release`
  in pair B. Red, gate G4. Same one-at-a-time rule as SA-503.
- **SA-602** `lighthouse-ci` in `lx-software` and pair B. Yellow.
- **SA-603** `cdk-deploy`. Write a design note in
  `actions/docs/plans/` first. It covers the parameters file format
  and how a value is marked as coming from a secret or a variable,
  how parameters route to stacks, the retry and recovery rules, and
  what each repository passes. The owner approves the note at gate
  G5. Then pilot in `findingalpha`, then `lx-software`, then pair B.
  This is C26.

### Stage 7. Parity and close-out

- **SA-701** Leftover duplication in pair B, by the rule in the
  catalog.
- **SA-702** Check parity. These touch product code, so each is its
  own yellow plan in the repository it changes: `mypy` wherever
  Python is linted, a type-check step for every Node app, a coverage
  floor set at each repository's measured value, and OpenAPI lint
  wherever an OpenAPI file exists.
- **SA-703** All four on `enforce`. Set this plan to `Done`. Record
  the open items that remain.

## Rollout procedure

For every pull request in a product repository.

1. Read that repository's `AGENTS.md` and `docs/architecture/zones.md`.
   For a yellow or red change, write a short plan in its `docs/plans/`
   from its template and link this plan. For red, wait for the gate.
2. Record the check-run names on the tip of `main`:
   `gh api repos/lx-software-ltd/<repo>/commits/<sha>/check-runs --paginate --jq '.check_runs[].name' | sort`.
3. Make the change. Update tests first where a test asserts workflow
   text.
4. Record the same list on the pull request head. The lists are equal,
   except for names the step says it changes. `lint` and `test` are
   always present.
5. Compare the replaced step's output before and after: finding
   counts, the list of files checked, or the diff summary.
6. Run the repository's own checks for workflow and script changes,
   as its `verify-change` skill lists them.
7. Open the pull request with the repository's template. State the
   zone, the gate if any, and the rollback.

## Rules for the executing agent

- One concern per pull request. An extraction does not change
  behaviour. A convergence row does not move code.
- `findingalpha` first, every time.
- Never write a red path without the gate named in chat.
- Never trigger a deploy, bootstrap, or key-management workflow.
- Never print the AWS account id, in a log, a document, or a pull
  request.
- Nothing private goes into `actions`.
- If a measured fact in this plan no longer holds, measure again and
  update the plan copy in `actions` before acting on it.
- If a step cannot produce its evidence, stop and report. Do not
  weaken the check to get a green run.

## Files

- `actions`: everything, new.
- Each product repository: `.github/workflows/*.yml`,
  `.github/dependabot.yml`, `.github/harness.json` (new),
  `.pre-commit-config.yaml`, the harness and PII scripts under
  `scripts/` and their tests (deleted), `scripts/deploy/**` where a
  deploy action replaces a script, and the documents that name those
  paths.
- `findingalpha` also: `scripts/test_workflow_secrets.py`.
- `lx-software` also:
  `docs/architecture/github-actions-trust-policy.json` (owner, O5).

## Invariants this change preserves

- A pull request to `main` cannot merge unless checks named `lint` and
  `test` pass, in every repository, at every step.
- A deploy runs only from `main`, in the `production` environment,
  through OIDC. No long-lived AWS key is added.
- No secret, account id, or personal data enters a log, a step
  summary, or the public `actions` repository.
- The PII hash list stays in each product repository. No plaintext
  entry is added anywhere.
- Every third-party action is pinned. After C01, by SHA.
- No extraction changes what a check accepts or rejects. Behaviour
  changes only through a register row.

## Done when

- Comparing the four repositories' workflow files finds no block of
  ten lines or more that two of them share.
- `workflow-conformance` runs in `enforce` mode and passes in all four
  and in `actions`.
- No caller passes an input that the register marks as temporary.
- The scripts named in SA-307 exist only in `actions`.
- Each deploy workflow has a green production run after its last
  change.
- `verify-rulesets` passes on its weekly run in all four.

## Rollback

- A product-repository change is a call-site or pin change. Revert the
  pull request. The inline steps come back from history.
- `actions` is fixed forward with a new commit. Old SHAs stay valid,
  because the ruleset blocks force-pushes and tag changes.
- A deploy-workflow change is rolled back the same way. The refactor
  does not touch stacks, so there is nothing to roll back in AWS.
- A convergence row that adds a check (C15, C16) can be rolled back by
  removing the job.

## Risks

- **One repository now sits in every pipeline.** A bad commit in
  `actions` cannot reach a caller until that caller's pin moves, which
  is the reason for SHA pins. The 7-day cooldown is lifted for
  `actions` so fixes arrive quickly. That also means a bad release
  arrives quickly. The pilot-first rule is the control.
- **`actions` is public and trusted by name.** D7 keeps it out of the
  AWS trust. Until O5 is done, the wildcard trust covers it.
- **A refactor can hide a behaviour change.** The before-and-after
  evidence in the rollout procedure is the control.
- **CI minutes rise in pair B** after C07.
- **Deleting or renaming `actions`** breaks every pinned caller.

## Open questions

For the owner:

- Which Node version is the organisation default (C04)?
- Which macOS runner label (C03)?
- Should `security-summary`, or at least `pii-denylist`, be a required
  check? Today only `lint` and `test` gate a merge, so a failing
  security job does not block one. The author would move
  `pii-denylist` under the `lint` gate.
- Is zero approving reviews on `main` intended (O4)?

Not verified:

- The organisation's Actions policy (O2). The API returns 403 to the
  agent.
- The live IAM trust policy. Only the document in `lx-software` was
  read.
- Whether `main-protection` has bypass actors. The field is hidden
  from the agent's token.
- How Dependabot treats a SHA pin that no tag points at, whether its
  `github-actions` ecosystem accepts a `directories` glob for the
  action subdirectories, and whether `cooldown` can exclude one
  dependency. SA-204 answers the first. Check the other two against
  the Dependabot documentation in SA-201.
- Whether Dependabot updates a `container.image` digest in a workflow
  file (C14). If not, bump it by hand.
- That `$GITHUB_ACTION_PATH/../lib` resolves inside the Semgrep
  container. The self-test in SA-303 proves or disproves it. The
  fallback is to copy the filter into the `semgrep` action directory.
- Why `evolvesprouts` checks out the pull request head SHA (C09).
