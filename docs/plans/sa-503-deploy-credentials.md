# Plan: SA-503 deploy credentials

**Status**: In progress
**Zone**: red

`.pre-commit-config.yaml` is red. This pull request changes only its `rev`, because workflow conformance allows one `lx-software-ltd/actions` commit and that rev has to be the same commit. The three deploy workflows are red. SA-503 was started in chat. No workflow is dispatched.

## Goal

Call `aws-oidc` from `deploy-backend.yml`, `deploy-admin-web.yml`, and `deploy-public-website.yml`. The account id is `secrets.AWS_ACCOUNT_ID` only. `required` stays at its default, true, so a missing account or region fails the job. `deploy-admin-web.yml` reads `UserPoolClientId`, `CognitoDomain`, and `AdminApiBaseUrl` with `cfn-stack-outputs`. The https checks stay in the workflow. The pin is `c210c3223782894251ba37b4fc71a0c245619d39`, the merge commit of actions#34, with a `# main 2026-11-22` comment.

## Non-goals

- No `manage-api-keys.yml` edit. It is not a deploy or promote workflow.
- No replacement of the public-website existence check. That check skips when `findingalpha-public-www` is absent. It does not read named outputs.
- No replacement of the inline bootstrap check in `deploy-backend.yml`. Removing `cdk bootstrap` from pair B is C24.
- No second actions commit. Every shared-action pin and the pre-commit rev move together.
- No account id in git. No deploy is dispatched. The owner runs the workflow after this merges (O7). The other three repositories wait until that run is green.

## Files

`.github/workflows/deploy-backend.yml`, `.github/workflows/deploy-admin-web.yml`, `.github/workflows/deploy-public-website.yml`, the other workflow pins, `.pre-commit-config.yaml`, `scripts/test_workflow_secrets.py`, this plan.

## Invariants this change preserves

- Each deploy job still runs only on `main`, in the production environment, with `id-token: write`.
- Email allowlists and the brief and SEC contacts still accept a secret or a variable. A variable still warns.
- Admin web still refuses a Cognito domain or API URL that is not `https://`.
- The public website still skips the upload when its stack is not deployed, and still fails on `AccessDenied`. `npm ci` and the build run before `aws-oidc`, so install scripts do not see the deploy role.
- Backend deploy still checks the domains, certificates, and email allowlist before it assumes the role. The inline bootstrap read stays.

## Done when

`python3 -m unittest scripts/test_workflow_secrets.py scripts/test_manage_public_api_keys.py` passes. Workflow conformance in enforce mode reports one actions commit.

## Rollback

Revert this pull request. The previous pin is `12ce7549f74db10a3c595214bf411deba0ef728a`.

## Open questions

None.
