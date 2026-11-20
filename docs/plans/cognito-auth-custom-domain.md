# Plan: Cognito custom Hosted UI on auth.<domain>

**Status**: Done
**Zone**: red (`backend/infrastructure/**`, `.github/workflows/deploy-*.yml`)

## Goal

Enable the Cognito Hosted UI on `auth.<domain>` the same way
`auth.lx-software.com` works in the sibling, but pass hostname and
certificate through GitHub environment variables like `api.<domain>`
(not through `params/production.json`).

## Non-goals

- Putting the domain or certificate ARN in git.
- Changing the Auth construct's prefix/custom domain conditions.
- Creating the Cloudflare `auth` record before the owner says go.

## Files

- `.github/workflows/deploy-backend.yml` — pass both Cognito custom-domain parameters
- `backend/infrastructure/lib/findingalpha-stack.ts` — conditional DNS target output
- `backend/infrastructure/test/findingalpha-stack.test.ts` — assert the output
- `docs/plans/reference.md`, `docs/plans/owner-checklist.md`,
  `docs/deployment/setup.md`, `docs/deployment/admin-website.md`

## Invariants this change preserves

- Empty name or empty certificate keeps the Cognito prefix domain.
- Domain hostnames and certificate ARNs stay out of git.
- Deploy Admin Web still reads `CognitoDomain` from the stack output.

## Done when

- `npm test` and `npm run build` in `backend/infrastructure` pass.
- `python3 -m unittest scripts.test_workflow_secrets` still passes.
- Owner can set the two vars, redeploy, then point DNS at the new output.

## Rollback

Unset the two GitHub variables and redeploy. The stack returns to the
prefix domain. Delete the `auth` DNS record if it was added.

## Open questions

None. Owner confirmed the ACM certificate already covers `auth.<domain>`.
