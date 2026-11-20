# AGENTS.md

## Cursor Cloud specific instructions

Applies to Cursor agents working in this repository. Path-scoped rules in `.cursor/rules/` attach for the area you edit. Procedures live in `.cursor/skills/*/SKILL.md`. `.cursorrules` is a pointer. Do not add rules there.

## Bootstrap

1. Always-applied constraints are in `.cursor/rules/00-repository-core.mdc`.
2. Read `docs/plans/00-overview.md` and `docs/plans/reference.md` before changing the system. `docs/architecture/overview.md` replaces the overview once milestone 2 writes it.

## Zones

Autonomy follows blast radius. The map is `docs/architecture/zones.md`. The stricter zone wins. If scope grows into a stricter zone, stop and ask.

- **Red.** Plan in chat and wait for explicit approval before any write.
- **Yellow.** Write a short plan under `docs/plans/` from `docs/plans/_template.md`, add or update tests first, then implement.
- **Green.** Implement and verify. Summarise intent in the pull request.

## Services

| Service | Path | Dev command | Port |
| --- | --- | --- | --- |
| Public www | `apps/public_www/` | `npm run dev` | 5173 |
| Admin console | `apps/admin_web/` | `npm run dev` | 5174 |
| Admin fixtures | `apps/admin_web/` | `npm run dev:mock` | 5174 |

Copy `apps/admin_web/.env.example` to `.env` for a real API. `npm run dev:mock` needs no AWS. Read `.cursor/skills/cursor-cloud/SKILL.md` before running services.

Lint and test with `npm run lint`, `npm test`, and `npm run build` in `apps/public_www`, `apps/admin_web`, and `backend/infrastructure`. Admin `npm test` runs Vitest. `npm run test:e2e` is the Playwright smoke.

## Evidence

A change is done when the `verify-change` skill's checks pass and the pull request template is filled in. Hooks format edits and block destructive shell commands. Cloud agents do not fire the `stop` hook. CI remains the merge gate.

## Hooks

`.cursor/hooks.json` denies force-push, pushes to `main`, `git reset --hard`, deleting `main`, `rm -rf` outside the repository and `/tmp`, `cdk deploy` and `cdk destroy`, `aws delete-*`, and `scripts/deploy/`. It asks before `git commit --amend`. A protected command is denied when it is the program being run, including inside `bash -c` or `$(...)`. Mentioning the same path in `git`, `rg`, or another reader is allowed.
