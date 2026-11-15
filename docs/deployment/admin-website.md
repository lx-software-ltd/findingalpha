# Deploying and operating the admin website

Runbook for the `findingalpha` and `findingalpha-admin-web` stacks and,
from M03, the admin SPA. Prerequisites are in [`setup.md`](./setup.md).
The architecture is in [`../architecture/overview.md`](../architecture/overview.md)
and [`../architecture/security.md`](../architecture/security.md).

Hostnames are `admin.<domain>`. The domain is a setting. It is not
written in this repository.

## Pre-deploy checklist

**Deploy Backend** runs on `main` when `backend/infrastructure/**`,
`backend/lambda/**`, `contracts/**`, or this workflow file change,
except `contracts/roadmap.json` alone. It can also be started with
**Run workflow**. Re-running a failed attempt uses the workflow from
that attempt. A fix to the workflow needs a new run.

1. **GitHub environment** — variables `AWS_REGION`,
   `CDK_BOOTSTRAP_QUALIFIER` (`siutindei`), `CDK_PARAM_FILE`,
   `ADMIN_WEB_DOMAIN_NAME`, `ADMIN_WEB_CERTIFICATE_ARN`,
   `ADMIN_GOOGLE_CLIENT_ID`, `ADMIN_COGNITO_ORIGIN`, and optionally
   `ADMIN_WAF_WEB_ACL_ARN`. Repository secret `AWS_ACCOUNT_ID`.
   Environment secrets `ADMIN_GOOGLE_CLIENT_SECRET`,
   `ADMIN_BOOTSTRAP_TEMP_PASSWORD` (14 or more characters, mixed
   classes, or user creation fails), `ADMIN_FEDERATED_EMAIL_ALLOWLIST`
   (comma-separated lower-case emails that receive `admin` — every
   Google admin and the bootstrap email), and `ADMIN_BOOTSTRAP_EMAIL`.
   The workflow stops immediately when the domain or the certificate is
   empty, or when the account id, the allow-list, or the bootstrap
   email is empty as both a secret and a variable. A set secret is
   used. The variable is the fallback, and the log shows it.
   **Deploy Admin Web** reads `UserPoolClientId`, `CognitoDomain`, and
   `AdminApiBaseUrl` from the `findingalpha` stack.
2. **Region** — `AWS_REGION` must be the region where the `siutindei`
   bootstrap parameter `/cdk-bootstrap/siutindei/version` exists.
3. **ACM** — `ADMIN_WEB_CERTIFICATE_ARN` must be an **ISSUED**
   certificate in **us-east-1** for `admin.<domain>`.
4. **Cloudflare** — proxy off (grey cloud) for certificate validation
   and for the `admin` CNAME. The developer adds that record only after
   the owner agrees.
5. **Google OAuth client** — add
   `https://<cognito-domain>/oauth2/idpresponse` to the authorized
   redirect URIs before the first Hosted UI sign-in. The owner does this.
6. **Docker / QEMU** — Python Lambdas bundle for `linux/arm64`.
   `deploy-backend.yml` and `cdk-diff.yml` register QEMU. For a
   template-only synth set `CDK_SKIP_PYTHON_PIP=1`.

An unlisted Google account is refused at sign-in (**This account is
not authorized.**). The variable is the complete admin list.

## 1. CDK Bootstrap and ACM

Do not bootstrap. The qualifier `siutindei` is already in place. See
[`setup.md`](./setup.md#3-cdk-bootstrap).

The owner requests a certificate for `admin.<domain>` in **us-east-1**,
validates it by DNS in Cloudflare with the proxy disabled, waits for
**ISSUED**, and sets `ADMIN_WEB_CERTIFICATE_ARN`.

## 2. Deploy admin infrastructure

Run **Deploy Backend**. Confirm both stacks finish:

- `findingalpha` — Cognito, DynamoDB, S3, HTTP API, the `findingalpha-tick` schedule
- `findingalpha-admin-web` — S3 origin and CloudFront for the SPA

**Deploy Admin Web** reads `UserPoolClientId`, `CognitoDomain` (the full
`https://` origin), and `AdminApiBaseUrl` from `findingalpha` when it
builds the SPA. The CloudFront domain is the DNS target for
`admin.<domain>`.

The deploy command names both stacks and does not use `--exclusively`.
The web stack imports the API origin from the backend stack.

If a deploy leaves `findingalpha` in `UPDATE_ROLLBACK_FAILED` on a
resource with no physical counterpart, the owner continues the rollback
skipping that logical id, then redeploys:

```bash
aws cloudformation continue-update-rollback \
  --stack-name findingalpha --resources-to-skip <logical-id>
```

### Admin web bucket policy

`findingalpha-admin-web` has one bucket policy on the origin bucket.
`enforceSSL` denies any request that is not TLS. Origin access control
adds the CloudFront `s3:GetObject` allow. The stack sets that
statement's `Sid` to `AllowCloudFrontServicePrincipalReadOnly`. S3 keeps
one policy per bucket, so the stack does not declare a second
`AWS::S3::BucketPolicy` on the same bucket. The log bucket has its own
TLS policy and is not the origin.

## 3. DNS and Google IdP

After the owner agrees, create a **CNAME** from `admin.<domain>` to the
CloudFront domain (Cloudflare proxy off). The owner adds the Cognito
`idpresponse` URL to the Google OAuth client. Do not edit Cognito app
client callback URLs in the console. CDK owns them from
`AdminWebDomainName` and overwrites drift.

## 4. Deploy the admin SPA

There is nothing to build until M03. **Deploy Admin Web** skips the
build while `apps/admin_web/package.json` is absent.

When the app exists, the workflow runs on `main` when `apps/admin_web/**`,
`scripts/deploy/deploy-admin-www.sh`, `contracts/roadmap.json`, or this
workflow file change, after a successful **Deploy Backend** on `main`,
or manually. Re-running a failed attempt uses the workflow from that
attempt. It builds
`apps/admin_web` with:

- `VITE_COGNITO_REDIRECT_URI` = `https://admin.<domain>/auth/callback`
- `VITE_COGNITO_LOGOUT_URI` = `https://admin.<domain>/`

The domain comes from `ADMIN_WEB_DOMAIN_NAME`. Then
`scripts/deploy/deploy-admin-www.sh` uploads hashed `dist/assets/**`
with a long immutable cache, uploads `index.html` with `no-cache`, and
invalidates CloudFront. The script reads `AdminWebBucketName` and
`AdminWebDistributionId` from `findingalpha-admin-web` (override with
`ADMIN_WEB_STACK_NAME`).

## 5. Smoke tests

Before the dashboard page exists (M03), check the API:

1. `GET <AdminApiBaseUrl>/health` returns 200 without a token.
2. `GET /me` without a token returns 401.
3. The Scheduler console shows `findingalpha-tick`. The records table
   gets `JOB#tick` run rows once the job handler records them.
4. Both secrets exist. Do not read their values.
5. Sign-in itself is tested in M03, when there is a page to sign in to.

When the page exists:

1. Open `https://admin.<domain>`. The login screen appears.
2. Sign in with Google (allow-listed email) or with the bootstrap email,
   and complete Hosted UI and MFA.
3. `GET /health` without auth returns 200. `GET /me` with
   `Authorization: Bearer <id_token>` returns 200.
4. Sign out, reload, and land on the login screen again.
5. A Google address that is not on `ADMIN_FEDERATED_EMAIL_ALLOWLIST` is
   refused with **This account is not authorized.** and no token.

## Auditing admin sign-ins

Every sign-in, token refresh and first federated sign-up passes through
`PreTokenGenerationFn`, which logs one JSON line per decision. In
CloudWatch Logs Insights, against that function's log group (the
`AuthPreTokenGenerationFnLogGroup` resource of the `findingalpha` stack):

```
fields @timestamp, email, username, trigger_source, decision, matched_admin,
       in_admin_group, allowlist_size
| filter tag = "admin_auth_gate"
| sort @timestamp desc
```

`decision` is `grant_admin` (email on the allow-list), `keep_admin_group`
(native bootstrap administrator), `deny_token`, `deny_sign_up`,
`allow_sign_up` or `allow_admin_create_user`. A `matched_admin: true`
line for an address you did not expect means that address is in
`ADMIN_FEDERATED_EMAIL_ALLOWLIST`. Remove it from that production
secret and run **Deploy Backend**. The next token refresh for that
account is refused.

## Local UI without a stack

There is no dashboard to run locally until M03. When `apps/admin_web`
exists, `npm run dev` needs a real Cognito pool and API. `npm run dev:mock`
loads a fake admin token for UI work. Never set `VITE_ADMIN_MOCK=1` on a
production build.
