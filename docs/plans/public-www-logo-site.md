# Plan: Public www logo site, login branding, and hosting

**Status**: Active
**Zone**: yellow for admin login (`apps/admin_web/src/**`); red for
hosting (`backend/infrastructure/**`, `scripts/deploy/**`,
`.github/workflows/deploy-*.yml`). Owner asked in chat to add CF/S3
hosting and the deploy script in this pull request.

## Goal

1. Public site at `apps/public_www` with only the Finding Alpha logo
   centred, plus a shared `favicon.ico` for public and admin.
2. Admin login page: dark background matching the public site, brand
   icon on top, no “findingalpha” copy, Google sign-in button shows
   only the Google logo.
3. CDK stack `findingalpha-public-www` (S3 + CloudFront), deploy script,
   and GitHub Actions workflow to publish `apps/public_www/dist`.

## Non-goals

- Marketing copy, analytics, or extra public routes.
- Changing authenticated admin chrome (still light Bootstrap).
- Creating DNS records (owner checklist; stop and ask before DNS).

## Files

- `apps/public_www/**`
- `apps/admin_web/src/pages/LoginPage.tsx`, `LoginPage.test.tsx`,
  `src/styles/shell.css`, `public/icon.png`, favicons, `index.html`
- `backend/infrastructure/lib/findingalpha-public-www-stack.ts`
- `backend/infrastructure/test/findingalpha-public-www-stack.test.ts`
- `backend/infrastructure/bin/app.ts`
- `scripts/deploy/deploy-public-website.sh`, `cdk-params.sh`
- `.github/workflows/deploy-public-website.yml`, `deploy-backend.yml`,
  `cdk-diff.yml`
- Docs: this plan, `reference.md`, `owner-checklist.md`,
  `docs/deployment/*`, `zones.md`, `AGENTS.md`

## Invariants this change preserves

- No secrets or personal data (including the live domain) in git.
- Public and admin origin buckets stay private, TLS-only, RETAIN.
- Paper-only / money paths untouched.
- Deploy still goes through GitHub Actions; agents do not run
  `cdk deploy` or `scripts/deploy/`.

## Done when

- `npm run lint`, `npm test`, `npm run build` in `apps/public_www` and
  `apps/admin_web`.
- `npm run build && npm test` in `backend/infrastructure`.
- Browser: dark login with icon + Google-only button; public logo page.
- Stack test asserts private buckets, HTTPS redirect, and outputs.

## Rollback

Revert the pull request. If the public stack was already deployed,
leave the stack in place and stop the deploy workflow; do not
`cdk destroy` from an agent.

## Open questions

- Owner must set GitHub vars `PUBLIC_WWW_DOMAIN_NAME` and
  `PUBLIC_WWW_CERTIFICATE_ARN`, then approve a Cloudflare DNS CNAME
  for the public hostname after the first stack deploy.
