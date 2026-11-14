# CDK parameter files

`production.json` is the file GitHub Actions reads when `CDK_PARAM_FILE`
points at it. Keys are `<stack>:<Parameter>`.

- `findingalpha:` goes to the backend stack.
- `findingalpha-admin-web:` goes to the dashboard stack.
- A key with no prefix, or with any other prefix, is an error.

Values that identify the owner or the account are not in this file. They
come from the GitHub `production` environment. See
[`docs/deployment/setup.md`](../../../docs/deployment/setup.md).

## Bootstrap

This repository does not bootstrap CDK and has no bootstrap workflow. It
reuses the existing bootstrap whose qualifier is `siutindei`. Set the
GitHub variable `CDK_BOOTSTRAP_QUALIFIER` to `siutindei`. Deploys read
`/cdk-bootstrap/siutindei/version`. Do not pass `--qualifier` to
`cdk deploy` or `cdk diff`.

## What belongs in the file

Committed rows are the non-secret defaults: the Cognito prefix, the
sender local part, the kill switches (all `false`), `BrokerMode` (`paper`),
and the knowledge-base caps. Leave a value out when it is empty. The
parameter's CloudFormation default applies.

Do not commit the dashboard hostname, the Google client, the allow-list,
the bootstrap email or password, mail recipients, or certificate ARNs.

## Local deploy

```bash
cd backend/infrastructure
export CDK_PARAM_FILE=params/production.json
export CDK_BOOTSTRAP_QUALIFIER=siutindei
npx cdk deploy --require-approval never
```

Pass the same owner-specific parameters the **Deploy Backend** workflow
passes. Secret parameters use `noEcho: true`.
