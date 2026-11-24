# Plan: M01 agent harness and repository skeleton

**Status**: Draft
**Zone**: red (hooks, pre-commit, PII tooling, contracts)

## Goal

Give the repository the same working rules as `lx-software` before any
product code exists: zones, rules, skills, hooks, checks, CI. After this
milestone a pull request that breaks a rule fails automatically.

## Non-goals

- No product code, no CDK app, no dashboard.
- No new rules. Every rule is copied or adapted from `lx-software`.
  The one new rule file, `engine.mdc`, restates sibling rules and the
  invariants in `00-overview.md` for the new code folder.
- No deploy workflows (M02).

## Files

Copied from `lx-software` and adapted:

- `AGENTS.md`, `.cursorrules`, `BUGBOT.md`, `SECURITY.md`, `pyproject.toml`
- `.pre-commit-config.yaml`
- `.cursor/rules/00-repository-core.mdc`, `infrastructure-cdk.mdc`,
  `admin-web.mdc`, `scripts.mdc`, and new `engine.mdc`
- `.cursor/skills/{verify-change,cursor-cloud,cdk-parameter,edit-contracts,add-admin-route}/SKILL.md`
  and new `.cursor/skills/add-engine-job/SKILL.md`
- `.cursor/hooks.json`, `.cursor/hooks/{guard_shell.sh,guard_shell.py,post_edit.py,stop_gate.py}`
- `.cursor/environment.json`, `.cursor/install.sh`
- `docs/architecture/zones.md`, `docs/research/README.md`,
  `docs/research/_template.md`
- `.github/PULL_REQUEST_TEMPLATE.md`, `.github/dependabot.yml`
- `.github/workflows/lint.yml`, `test.yml`, `security.yml`,
  `check-lockfiles.yml`
- `scripts/validate_agent_rules.py`, `check_file_length.py`,
  `check_test_focus.py`, `check_pii.py`, `check-pii.sh`,
  `file-length-allowlist.txt`, `pii-denylist.sha256`
- `scripts/test_agent_hooks.py`, `test_harness_ratchets.py`,
  `test_check_pii.py`
- `scripts/sync-contracts.py`, `scripts/check-contracts.py`

New:

- `.gitignore` (edited)
- `contracts/README.md`, `contracts/roadmap.json`

## Invariants this change preserves

- Rules come from the sibling repositories. Nothing is invented.
- `.cursorrules` stays a pointer of at most 8 lines.
- `AGENTS.md` stays at most 60 lines, each rule file at most 80, each
  skill at most 160.
- Every rule bullet ends with a `[why: ...]` tag.
- The PII denylist holds digests only.

## Steps

### M01-T01 Fix `.gitignore`

The current file is GitHub's Python template. It ignores `lib/`,
`dist/` and `build/` anywhere. That would silently hide
`backend/infrastructure/lib/` and `apps/admin_web/src/lib/`.

1. Remove the lines `lib/`, `lib64/`, `build/`, `dist/`, `var/`,
   `parts/`, `downloads/`, `eggs/`, `sdist/`, `wheels/`.
2. Add:
   ```
   node_modules/
   cdk.out/
   cdk.context.json
   apps/admin_web/dist/
   apps/admin_web/playwright-report/
   apps/admin_web/test-results/
   backend/infrastructure/dist/
   .env
   .env.local
   *.pdf
   ```
   `*.pdf` is there so nobody commits a book by accident.
3. Check: `mkdir -p backend/infrastructure/lib && touch backend/infrastructure/lib/x.ts && git check-ignore -v backend/infrastructure/lib/x.ts`
   prints nothing. Remove the test file.

### M01-T02 Zones

Copy `docs/architecture/zones.md`. Replace the path lists with:

Red:

- `backend/infrastructure/**`
- `backend/lambda/pre_token_generation/**`
- `_require_admin` in `backend/lambda/engine/http_common.py`
- `backend/lambda/engine/broker.py`, `broker_alpaca.py`, `orders.py`,
  `leverage.py`, `limits.py`, `kill_switch.py`, `breakers.py`,
  `holds.py`
- `contracts/**` except `contracts/roadmap.json`
- `scripts/deploy/**`
- `scripts/check-pii.sh`, `scripts/check_pii.py`, `scripts/pii-denylist.sha256`
- `.github/workflows/deploy-*.yml`
- `.cursor/hooks.json`, `.cursor/hooks/**`
- `.pre-commit-config.yaml`

Yellow:

- Remaining `backend/lambda/**`
- `apps/admin_web/src/**`

Green:

- `docs/**`
- `contracts/roadmap.json`
- Test-only edits that do not sit on a red path

Keep the opening and closing paragraphs of the sibling file unchanged.
Add one sentence under Red: "The listed engine files can move money or
change limits."

### M01-T03 `AGENTS.md`, `.cursorrules`, `BUGBOT.md`, `SECURITY.md`

1. Copy all four.
2. In `AGENTS.md` keep the headings `## Cursor Cloud specific instructions`,
   `## Bootstrap`, `## Zones`, `## Services`, `## Evidence`, `## Hooks`.
   The check requires the strings `## Zones`,
   `docs/architecture/zones.md` and `## Cursor Cloud`.
3. Services table: one row for the admin console (`apps/admin_web/`,
   `npm run dev`, 5174) and one for fixtures (`npm run dev:mock`, 5174).
   Remove the public website.
4. Bootstrap: point at `docs/plans/00-overview.md` and
   `docs/plans/reference.md` until `docs/architecture/overview.md`
   exists.
5. Hooks paragraph: remove the scripts that do not exist here.
6. `BUGBOT.md` and `SECURITY.md`: replace product names. Remove
   sections about features this repository does not have. Do not add a
   contact email. Point security reports at GitHub private
   vulnerability reporting.
7. Check: `wc -l AGENTS.md` is at most 60 and `.cursorrules` at most 8.

### M01-T04 Rules

Copy the four rule files, then write `engine.mdc`.

- `00-repository-core.mdc`: keep `alwaysApply: true` and no `globs`.
  Keep the bullets about secrets, `noEcho`, personal data, fictional
  test people, contracts sync, npm lockfiles, TypeScript style, no
  Tailwind, no `print()`, `unittest` naming. Remove bullets about the
  public website.
- `infrastructure-cdk.mdc`: keep as is, with stack names replaced.
- `admin-web.mdc`: keep the bullets about mock mode, Bootstrap, the API
  client, session storage, tests.
- `scripts.mdc`: keep the bullets about script tests, deploy scripts,
  contracts sync and the denylist. Remove bullets about scripts that do
  not exist here.
- `engine.mdc` (`globs: backend/lambda/engine/**`), adapted from
  `backend-admin.mdc` and `board.mdc`. Bullets:
  - Every model call goes through `openrouter_client.py` with data
    collection denied.
  - No model call inside an HTTP request. Long work is a job with a job
    row and the page polls.
  - Kill switches fail closed.
  - Holds and approvals are separate record types.
  - Spend is recorded on `USAGE#<date>` rows and checked before each
    call.
  - Schedules are EventBridge Scheduler with an IAM-role target and an
    explicit time zone.
  - A model never produces a number that sizes or prices an order.
  - Formulas and thresholds come from `contracts/methodology.json`.
  - The broker host is the paper host unless `BROKER_MODE` is `live`.
  - No file over 500 lines.

**The `[why:]` trap.** `validate_agent_rules.py` reads every word of 7
or more characters made only of `0-9a-f` as a commit id and requires
that commit to exist in this repository. The sibling commit ids do not
exist here. So every tag must read `[why: convention ...]` and contain
no such word. Write `[why: convention from lx-software, shared
contracts]`, not a commit id. Words such as "defaced" or "effaced"
would also trip it.

Check: `python3 scripts/validate_agent_rules.py` (after T06).

### M01-T05 Skills

Copy `verify-change`, `cursor-cloud`, `cdk-parameter`, `edit-contracts`,
`add-admin-route`. Replace paths and names. In `verify-change` the
Lambda line becomes:

```
python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py' -v
```

Write `add-engine-job/SKILL.md` (front matter `name: add-engine-job` and
a `description`). Content, as a numbered procedure: add the job to
`contracts/jobs.json`; sync contracts; add the handler function and
register it in `jobs_handler.py`; wrap it with `job_runs.record`; check
its kill switch first; add the schedule in CDK if it is scheduled (red
zone); add it to the manual-run allow-list only if it is safe to run
twice; write the unit test; update `reference.md` section 9.

### M01-T06 Check scripts

1. Copy the five check scripts, the allowlist and the three test files.
2. `validate_agent_rules.py`: set
   ```python
   REQUIRED_RULES = {
       CORE_RULE: True,
       "admin-web.mdc": False,
       "infrastructure-cdk.mdc": False,
       "engine.mdc": False,
       "scripts.mdc": False,
   }
   REQUIRED_SKILLS = (
       "verify-change",
       "cursor-cloud",
       "cdk-parameter",
       "edit-contracts",
       "add-admin-route",
       "add-engine-job",
   )
   ```
3. `file-length-allowlist.txt`: keep the four comment lines, no entries.
4. `check_file_length.py` and `check_test_focus.py`: no change. They
   already scan `backend/lambda`, `backend/infrastructure/lib` and
   `apps`.
5. `scripts/pii-denylist.sha256`: one comment line. The owner supplies
   the digests (owner task O03). Do not create digests yourself and do
   not ask for the plain values.
6. `test_harness_ratchets.py` and `test_agent_hooks.py` name sibling
   files and scripts. Remove the cases about scripts that do not exist
   here. Keep every case about force-push, `main`, `reset --hard`,
   `rm -rf`, `cdk deploy`, `aws delete-*`, deploy scripts, amend.
7. Check: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`.

### M01-T07 Hooks

1. Copy `.cursor/hooks.json` and the four hook files unchanged except:
2. In `guard_shell.py` `_live_mutation`, keep the `scripts/deploy/` rule
   and delete the branches for scripts that do not exist here. Remove
   `API_KEY_VERBS` if nothing uses it. Do not add new deny rules in
   this milestone.
3. `stop_gate.py`: unchanged.
4. `chmod +x` the hook files. Check:
   `echo '{"command":"git push --force"}' | .cursor/hooks/guard_shell.sh`
   prints a deny decision.

### M01-T08 Contracts skeleton

1. `contracts/README.md`: copy and replace the generated-artifact list
   with the four paths in `reference.md` section 7.
2. `contracts/roadmap.json`: build it from this plan. Shape:
   ```json
   {
     "version": 1,
     "milestones": [
       {
         "id": "M01",
         "title": "Agent harness and repository skeleton",
         "plan": "docs/plans/01-agent-harness.md",
         "zone": "red",
         "status": "in_progress",
         "dependsOn": [],
         "pullRequests": [],
         "steps": [
           { "id": "M01-T01", "title": "Fix .gitignore", "status": "done" }
         ]
       }
     ],
     "ownerTasks": [
       { "id": "O01", "title": "Choose and register the new domain", "blocks": ["M02"] }
     ]
   }
   ```
   Milestone status is one of `not_started`, `in_progress`, `blocked`,
   `done`. Step status is `todo`, `doing` or `done`. Include every step
   id from every milestone file and every owner task from
   `owner-checklist.md`. `pullRequests` is a list of URLs.
3. `scripts/sync-contracts.py`: the sibling script is 639 lines and
   mostly about sibling contracts. Write a small version with the same
   command-line behaviour: read every `contracts/*.json`, copy them
   (except `roadmap.json`, which the Lambda does not need) to
   `backend/lambda/engine/contracts/`, and write
   `apps/admin_web/src/lib/contracts/generated.ts` with one exported
   `as const` object per file. For now only the roadmap exists. Skip an
   output whose parent folder does not exist yet and print a note.
4. `scripts/check-contracts.py`: run the sync into a temporary folder
   and fail if any generated file differs from the committed one. Also
   validate the roadmap: unique ids, known status values, every
   `dependsOn` and `blocks` id exists.
5. Tests: `scripts/test_sync_contracts.py`.

### M01-T09 Python and pre-commit config

1. Copy `pyproject.toml`. Change the per-file ignore for the sibling
   script to nothing. Keep `"backend/lambda/**/test_*.py" = ["E402"]`.
2. Copy `.pre-commit-config.yaml`. Remove the public-website ESLint
   hook. Keep the admin-web hook.

### M01-T10 CI workflows

Copy and trim. Keep the runner image, action versions and the
aggregator pattern exactly as the sibling has them.

- `lint.yml`: jobs `lint-admin-web`, `lint-cdk`, `lint-python`,
  `validate-agent-harness`, and the aggregator `lint`. Remove
  `lint-web`. Until M02 and M03 create the folders, guard the two Node
  jobs with a first step that exits successfully when
  `package.json` is missing:
  ```yaml
  - name: Skip when the app does not exist yet
    id: exists
    run: test -f apps/admin_web/package.json && echo "present=true" >> "$GITHUB_OUTPUT" || echo "present=false" >> "$GITHUB_OUTPUT"
  ```
  and put `if: steps.exists.outputs.present == 'true'` on the later
  steps. Remove the guards in the milestone that creates the folder.
- `test.yml`: jobs `check-contracts`, `test-python` (new, see below),
  `build-admin-web`, `e2e-admin-web`, `test-infrastructure`, and the
  aggregator `test`. Remove `test-web`. Same guards.
  `test-python`:
  ```yaml
  test-python:
    name: Test Python
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - run: python3 -m pip install boto3
      - run: |
          for dir in backend/lambda/engine backend/lambda/pre_token_generation; do
            if [ -d "$dir" ]; then
              python3 -m unittest discover -s "$dir" -p 'test_*.py' -v
            fi
          done
  ```
  Add `test-python` to the aggregator's `needs` and to its Python list.
- `security.yml`: keep Checkov, CodeQL, PII denylist, secret scanning,
  Semgrep and the summary. Remove steps that name sibling stacks.
- `check-lockfiles.yml`: directory list becomes
  `apps/admin_web backend/infrastructure`.
- `.github/dependabot.yml`: keep `github-actions`,
  `/apps/admin_web`, `/backend/infrastructure`, and change the pip
  entry to `/backend/lambda/engine`. Remove `/apps/public_www`. Keep
  the `ignore` comments only if the same packages appear here.
- `.github/PULL_REQUEST_TEMPLATE.md`: copy unchanged.

The aggregator jobs must be named exactly `lint` and `test`. Branch
protection (owner task O02) requires those names.

### M01-T11 Cloud agent environment

1. `.cursor/environment.json`: name `findingalpha`, install
   `bash .cursor/install.sh`, one terminal:
   `cd apps/admin_web && npm run dev:mock -- --host --port 5174`.
2. `.cursor/install.sh`: copy. Remove the public website block. Wrap
   each `npm ci` in a test for `package.json` so the script works
   before M02 and M03. Keep the placeholder `.env` block.

### M01-T12 Research templates and README

Copy `docs/research/README.md` and `_template.md`. Update the root
`README.md` with a short "Working here" section that points at
`AGENTS.md`.

## Done when

- `python3 scripts/validate_agent_rules.py` passes.
- `python3 scripts/check_file_length.py`, `check_test_focus.py`,
  `check_pii.py`, `check-contracts.py` pass.
- `python3 -m ruff check scripts .cursor/hooks` passes.
- `python3 -m unittest discover -s scripts -p 'test_*.py' -v` passes.
- The pull request shows the checks `lint` and `test` green.
- A second, throwaway pull request that adds a rule bullet without a
  `[why:]` tag fails `lint`. Close it without merging and link it in
  the Evidence section.

## Rollback

Revert the pull request. Nothing is deployed.

## Open questions

- Owner task O03 (denylist digests). The check passes with an empty
  list, so this does not block the merge, but the list must be filled
  before M02 adds the first files that could carry personal data.
