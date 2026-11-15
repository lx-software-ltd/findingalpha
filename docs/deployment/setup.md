# Deployment setup (AWS + GitHub Actions)

One-time prerequisites for **Deploy Backend** and **Deploy Admin Web**.
Do these before [`admin-website.md`](./admin-website.md).

This repository does not create a CDK bootstrap and has no bootstrap
workflow. It reuses the existing bootstrap with qualifier `siutindei`.

## 1. GitHub OIDC provider

**IAM → Identity providers → Add provider**, if the account does not
already have it.

- Provider type: **OpenID Connect**
- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

## 2. `GitHubActionsRole`

The workflows assume an IAM role named `GitHubActionsRole`. This
repository does not create that role. The role that already deploys the
sibling stacks is reused, once it trusts this repository and can assume
the `siutindei` bootstrap roles.

### Trust

The role's trust policy must allow `token.actions.githubusercontent.com`
to assume it for this repository, including the `production` environment
subject and pull-request subjects. Confirm which subject format the
repository issues before editing the trust policy.

### Permissions

CDK deploys through the roles created by the existing bootstrap. The
role must be able to assume them and read the bootstrap version
parameter. `QUALIFIER` here is `siutindei`:

```json
{
  "Effect": "Allow",
  "Action": "sts:AssumeRole",
  "Resource": [
    "arn:aws:iam::ACCOUNT_ID:role/cdk-siutindei-deploy-role-*",
    "arn:aws:iam::ACCOUNT_ID:role/cdk-siutindei-lookup-role-*",
    "arn:aws:iam::ACCOUNT_ID:role/cdk-siutindei-file-publishing-role-*",
    "arn:aws:iam::ACCOUNT_ID:role/cdk-siutindei-image-publishing-role-*"
  ]
}
```

```json
{
  "Effect": "Allow",
  "Action": "ssm:GetParameter",
  "Resource": "arn:aws:ssm:*:ACCOUNT_ID:parameter/cdk-bootstrap/*"
}
```

For the two stacks (`findingalpha`, `findingalpha-admin-web`) the role
also needs:

- **CloudFormation** `DescribeStacks` on
  `arn:aws:cloudformation:REGION:ACCOUNT_ID:stack/findingalpha/*` and
  `arn:aws:cloudformation:REGION:ACCOUNT_ID:stack/findingalpha-admin-web/*`.
  **Deploy Admin Web** reads `UserPoolClientId`, `CognitoDomain`, and
  `AdminApiBaseUrl` from `findingalpha` before it uploads the SPA.
- **S3** `GetObject` / `PutObject` / `DeleteObject` / `ListBucket` on the
  dashboard bucket (`findingalpha-web-*`).
- **CloudFront** `CreateInvalidation` on the dashboard distribution.

Resource names this role may create must include the `findingalpha*`
prefix. That is an owner check, not something this repository can grant.

## 3. CDK Bootstrap

Already done, with qualifier `siutindei`, in the account and region
these stacks use. Do not run `cdk bootstrap` again from this repository.
There is no **CDK Bootstrap** workflow here.

The deploy jobs read `/cdk-bootstrap/siutindei/version` when
`CDK_BOOTSTRAP_QUALIFIER` is `siutindei`. CloudFront certificates for
`admin.<domain>` are requested in `us-east-1`. That certificate is an
owner task. This repository does not request it.

## 4. GitHub environment (`production`)

Repository variables, also read by **CDK Diff** on pull requests:
`AWS_REGION`, `CDK_BOOTSTRAP_QUALIFIER` (`siutindei`), `CDK_PARAM_FILE`
(`backend/infrastructure/params/production.json`). The account id is
read from the secret `AWS_ACCOUNT_ID`, and from the variable of the
same name when that secret is empty. A secret is masked in the log. A
variable is printed, so replace it with the secret and then delete the
variable. Until both the account id and `AWS_REGION` are unset, the
`diff` check passes with a warning and does not compare the account.
Once either source has the account id, it writes the diff to the job
summary and fails on a real error. It is not a required check, so it
does not block a merge. A Dependabot pull request receives Dependabot
secrets, not Actions secrets. It can still read the variable. Add
`AWS_ACCOUNT_ID` under Settings, Secrets and variables, Dependabot,
before deleting the variable.

Environment `production` variables:

| Variable | Purpose |
| --- | --- |
| `AWS_REGION` | Target region. Must match the existing `siutindei` bootstrap. |
| `CDK_BOOTSTRAP_QUALIFIER` | `siutindei`. |
| `CDK_PARAM_FILE` | `backend/infrastructure/params/production.json`. |
| `ADMIN_WEB_DOMAIN_NAME` | `admin.<domain>`. Required. The deploy fails when this is empty. |
| `ADMIN_WEB_CERTIFICATE_ARN` | ACM certificate in us-east-1, status ISSUED. Required. The account id inside the ARN is masked in logs because `AWS_ACCOUNT_ID` is a secret. |
| `ADMIN_GOOGLE_CLIENT_ID` | Google OAuth client id. It also appears in the browser during sign-in. |
| `ADMIN_COGNITO_ORIGIN` | `https://findingalpha-admin-auth.auth.<region>.amazoncognito.com`, or `https://auth.<domain>` when the custom Hosted UI domain is set. |
| `ADMIN_WAF_WEB_ACL_ARN` | Optional. Empty leaves the web ACL off. |
| `MAIL_SENDING_DOMAIN` | `<domain>`. Empty disables email. |

Secrets:

| Secret | Where | Purpose |
| --- | --- | --- |
| `AWS_ACCOUNT_ID` | Repository | Target account. Used when set. The variable of the same name is the fallback, and the log shows it. |
| `AWS_ACCOUNT_ID` | Dependabot | The same value, so `cdk-diff` still runs on a Dependabot pull request. |
| `ADMIN_GOOGLE_CLIENT_SECRET` | Environment `production` | Google OAuth client secret (`noEcho`). |
| `ADMIN_BOOTSTRAP_TEMP_PASSWORD` | Environment `production` | Bootstrap password, 14 or more characters (`noEcho`). |
| `ADMIN_FEDERATED_EMAIL_ALLOWLIST` | Environment `production` | Comma-separated lower-case emails that may sign in. The variable is the fallback until this secret exists. |
| `ADMIN_BOOTSTRAP_EMAIL` | Environment `production` | Bootstrap user email. The variable is the fallback until this secret exists. |
| `BRIEF_RECIPIENT_EMAIL` | Environment `production` | Where the daily email will go. Unset until that milestone. |
| `SEC_CONTACT_EMAIL` | Environment `production` | Contact address in the SEC User-Agent. Unset until ingest. |

Do not put any of these values in git. Copy a variable into the secret
of the same name, then delete the variable. Until the secret exists,
the deploy uses the variable and the log shows the value. The deploy
fails only when both are empty.

## Troubleshooting

**`SSM parameter /cdk-bootstrap/siutindei/version` not found.** The
qualifier variable is unset or wrong, the role cannot read the
parameter, or this job is pointed at a region that was not bootstrapped.
Stop and tell the owner. Do not bootstrap a second qualifier from here.

**`current credentials could not be used to assume … deploy-role`.**
`GitHubActionsRole` is missing `sts:AssumeRole` on the `cdk-siutindei-*`
roles, or those roles do not trust it.
