# Admin website

Runbook for stacks `findingalpha` and `findingalpha-admin-web`.
Prerequisites are in [setup.md](setup.md).

## Pre-deploy checklist

1. GitHub environment `production` has `ADMIN_WEB_DOMAIN_NAME`
   (`admin.<domain>`), `ADMIN_WEB_CERTIFICATE_ARN`, `ADMIN_COGNITO_ORIGIN`,
   `ADMIN_GOOGLE_CLIENT_ID`, `ADMIN_FEDERATED_EMAIL_ALLOWLIST` and
   `ADMIN_BOOTSTRAP_EMAIL`. Secrets `ADMIN_GOOGLE_CLIENT_SECRET` and
   `ADMIN_BOOTSTRAP_TEMP_PASSWORD` are set. **Deploy Backend** fails
   closed when the domain or the certificate variable is empty.
2. `AWS_REGION` is the region where `/cdk-bootstrap/siutindei/version`
   exists.
3. The certificate is **ISSUED** in **us-east-1** for `admin.<domain>`.
4. DNS records are created only after the owner says go, and they are
   DNS-only (proxy off).
5. The Google OAuth client lists
   `https://findingalpha-admin-auth.auth.<region>.amazoncognito.com/oauth2/idpresponse`
   before the first sign-in.
6. Template-only synth uses `CDK_SKIP_PYTHON_PIP=1`. Deploy workflows
   register QEMU so the arm64 bundle builds on the runner.

## 1. CDK Bootstrap and ACM

The bootstrap is reused. Request the `admin.<domain>` certificate in
us-east-1, validate it by DNS, wait until it is issued, and put the ARN
in `ADMIN_WEB_CERTIFICATE_ARN`.

## 2. Deploy admin infrastructure

**Deploy Backend** updates `findingalpha` and `findingalpha-admin-web`
together. It does not pass `--exclusively`.

A stack stuck in `UPDATE_ROLLBACK_FAILED` is continued by the owner:

```bash
aws cloudformation continue-update-rollback \
  --stack-name findingalpha --resources-to-skip <logical-id>
```

Buckets, tables, the key and the user pool are retained. Do not delete
them by hand.

### Admin web bucket policy

The origin bucket has one policy: the TLS deny from `enforceSSL` and
the CloudFront read statement
`AllowCloudFrontServicePrincipalReadOnly`. There is no second bucket
policy resource on that bucket.

## 3. DNS and Google IdP

After the owner says go, create a CNAME from `admin.<domain>` to the
`AdminWebDistributionDomain` output. Proxy off. Add the Cognito
`idpresponse` URL to the Google client. CDK owns the app client
callback URLs.

## 4. Deploy the admin SPA

**Deploy Admin Web** builds `apps/admin_web` and runs
`scripts/deploy/deploy-admin-www.sh`. The script reads
`AdminWebBucketName` and `AdminWebDistributionId` from
`findingalpha-admin-web`. Hashed assets are cached for a year.
`index.html` is uploaded last with `no-cache`, then CloudFront is
invalidated.

The build sets `VITE_COGNITO_REDIRECT_URI` to
`https://admin.<domain>/auth/callback` and `VITE_COGNITO_LOGOUT_URI` to
`https://admin.<domain>/`. The client id, Hosted UI origin and API URL
come from stack outputs.

## 5. Smoke tests

1. `GET <AdminApiBaseUrl>/health` returns 200 without a token.
2. `GET /me` without a token returns 401.
3. Scheduler shows `findingalpha-tick`, and the records table gets
   `JOB#tick` rows.
4. Both secrets exist. Do not read their values.
5. After the dashboard exists: the login screen loads, an allow-listed
   user can sign in, and an address that is not on the list is refused.

## Auditing admin sign-ins

`PreTokenGenerationFn` logs one JSON line per decision. In CloudWatch
Logs Insights:

```
fields @timestamp, email, trigger_source, decision
| filter tag = "admin_auth_gate"
| sort @timestamp desc
```

`decision` is `grant_admin`, `keep_admin_group`, `deny_token` or
`deny_sign_up`. An unexpected `grant_admin` means that address is on
`ADMIN_FEDERATED_EMAIL_ALLOWLIST`. Remove it and run **Deploy Backend**.

## Local UI without a stack

From `apps/admin_web`, `npm run dev:mock` serves the dashboard with
`VITE_ADMIN_MOCK=1` and no AWS account. Do not set that variable on a
production build.
