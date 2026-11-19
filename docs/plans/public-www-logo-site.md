# Plan: Public www logo site and shared favicon

**Status**: Active
**Zone**: green (`apps/public_www/**`, `apps/admin_web/public/**`,
`apps/admin_web/index.html`, docs, CI lockfile/lint/test wiring).
Hosting and deploy workflows stay red and are out of scope.

## Goal

Add a public site at `apps/public_www` that shows only the Finding Alpha
logo centred on a dark page, matching the sibling `apps/public_www`
layout convention. Generate `favicon.ico` from the brand icon and serve
it from both the public site and the admin console.

## Non-goals

- CloudFront / S3 / certificate / DNS for `www.<domain>` (red:
  `backend/infrastructure/**`, `.github/workflows/deploy-*.yml`).
- Marketing copy, contact forms, analytics, or extra routes.

## Files

- `apps/public_www/**` — Vite React app, logo page, favicons, tests
- `apps/admin_web/public/favicon.ico` (+ svg/png/apple-touch)
- `apps/admin_web/index.html` — link the new favicon set
- `AGENTS.md`, `docs/plans/reference.md`, `docs/architecture/zones.md`
- `.github/workflows/{check-lockfiles,lint,test}.yml`, dependabot,
  `.cursor/install.sh`, `.cursor/skills/cursor-cloud/SKILL.md`

## Invariants this change preserves

- No secrets or personal data in git.
- No CDK or deploy-script changes.
- Admin console behaviour and routes unchanged aside from favicon links.

## Done when

- `npm run lint`, `npm test`, and `npm run build` pass in
  `apps/public_www`.
- `npm run build` still passes in `apps/admin_web`.
- Browser check: public page shows only the centred logo; both apps
  serve `favicon.ico`.

## Rollback

Revert the pull request. No deployed public stack exists yet.

## Open questions

- Approve a follow-up red-zone change for a
  `findingalpha-public-www` stack and deploy workflow, copied from
  `lx-software`.
