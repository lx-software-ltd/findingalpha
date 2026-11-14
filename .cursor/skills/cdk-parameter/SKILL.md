---
name: cdk-parameter
description: Add a CDK parameter, a params file entry, and the Jest assertion.
---

# Add a CDK parameter

1. Add the `CfnParameter` in `backend/infrastructure/lib/parameters.ts`. Secret values set `noEcho: true`.
2. Add the key to `backend/infrastructure/params/production.json` as `<stack>:<Parameter>`. Values that identify the owner come from the GitHub `production` environment, not from the file.
3. Pass the value into the Lambda environment with the short name from `docs/plans/reference.md` section 4.
4. Extend the Jest assertions in `backend/infrastructure/test` so the parameter default and `allowedValues` match the plan.
5. Mention the parameter in `docs/deployment/admin-website.md` when an operator has to set it.
