# Deployment setup

One-time prerequisites. The CDK bootstrap with qualifier `siutindei`
already exists in this account and region. This repository has no
bootstrap workflow and does not run `cdk bootstrap`.

## 1. GitHub OIDC provider

The account already has the provider used by `lx-software`.

- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

## 2. `GitHubActionsRole`

Workflows assume the existing role `GitHubActionsRole`. Its trust policy
must allow this repository:

- `repo:lx-software-ltd/findingalpha:environment:production`
- `repo:lx-software-ltd/findingalpha:pull_request`

The role must be able to assume the bootstrap roles
`cdk-siutindei-deploy-role-*`, `cdk-siutindei-file-publishing-role-*`,
`cdk-siutindei-image-publishing-role-*` and `cdk-siutindei-lookup-role-*`,
and to read `/cdk-bootstrap/siutindei/version`.

It also needs CloudFormation on stacks named `findingalpha` and
`findingalpha-admin-web`, S3 and CloudFront access to the dashboard
bucket and distribution, and (for the API-key workflow added later)
item access on `findingalpha-records` plus decrypt on the shared key.

## 3. Bootstrap

Do not bootstrap again. Deploy jobs check
`/cdk-bootstrap/siutindei/version` in `ap-southeast-1`. The dashboard
certificate is requested in `us-east-1` and is not created by this
repository.

## 4. GitHub environment `production`

Repository variables: `AWS_ACCOUNT_ID`, `AWS_REGION` (`ap-southeast-1`),
`CDK_BOOTSTRAP_QUALIFIER` (`siutindei`), `CDK_PARAM_FILE`
(`backend/infrastructure/params/production.json`).

Environment variables for the first deploy: `ADMIN_WEB_DOMAIN_NAME`,
`ADMIN_WEB_CERTIFICATE_ARN` (us-east-1), `ADMIN_COGNITO_ORIGIN`,
`ADMIN_GOOGLE_CLIENT_ID`, `ADMIN_FEDERATED_EMAIL_ALLOWLIST`,
`ADMIN_BOOTSTRAP_EMAIL`. Optional later: `SEC_CONTACT_EMAIL`,
`MAIL_SENDING_DOMAIN`, `BRIEF_RECIPIENT_EMAIL`, `ADMIN_WAF_WEB_ACL_ARN`,
`ADMIN_COGNITO_CUSTOM_DOMAIN_CERTIFICATE_ARN`.

Secrets: `ADMIN_GOOGLE_CLIENT_SECRET`, `ADMIN_BOOTSTRAP_TEMP_PASSWORD`
(14 or more characters). `PUBLIC_API_KEY_GPG_PASSPHRASE` is added with
the API-key workflow.

AWS access keys, the Alpaca key and the OpenRouter key are not GitHub
secrets. The broker and model keys go in Secrets Manager after deploy.
