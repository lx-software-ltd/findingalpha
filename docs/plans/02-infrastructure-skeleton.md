# Plan: M02 infrastructure skeleton

**Status**: Built. The password bootstrap user and TOTP enrolment described below were removed. Sign-in is Google only.
**Zone**: red

## Goal

Two CDK stacks that deploy from GitHub Actions and give: encrypted
storage, Cognito sign-in with the `admin.lx-software.com` strategy, an
HTTP API with two trivial routes, web hosting for the dashboard, one
schedule, and all kill switches off. After this milestone the platform
exists and does nothing.

## Non-goals

- No business logic. `EngineFn` only knows the jobs `noop` and `tick`.
- No knowledge base resources (M07). No SES identity (M10).
- No VPC, NAT gateway, RDS, or provisioned capacity.
- No new CDK bootstrap. The existing `siutindei` bootstrap is reused.

## Files

```
backend/scripts/run-cdk-app.sh
backend/infrastructure/package.json  package-lock.json  tsconfig.json
backend/infrastructure/jest.config.js  cdk.json
backend/infrastructure/bin/app.ts
backend/infrastructure/lib/findingalpha-stack.ts
backend/infrastructure/lib/findingalpha-admin-web-stack.ts
backend/infrastructure/lib/parameters.ts
backend/infrastructure/lib/data.ts
backend/infrastructure/lib/secrets.ts
backend/infrastructure/lib/functions.ts
backend/infrastructure/lib/api-routes.ts
backend/infrastructure/lib/http-api.ts
backend/infrastructure/lib/schedules.ts
backend/infrastructure/lib/alarms.ts
backend/infrastructure/lib/outputs.ts
backend/infrastructure/lib/shared-contracts.ts        (generated)
backend/infrastructure/lib/constructs/auth.ts
backend/infrastructure/lib/constructs/python-lambda.ts
backend/infrastructure/lib/constructs/checkov-suppressions.ts
backend/infrastructure/params/production.json  README.md
backend/infrastructure/test/findingalpha-stack.test.ts
backend/infrastructure/test/findingalpha-admin-web-stack.test.ts
backend/infrastructure/test/python-lambda.test.ts
backend/lambda/pre_token_generation/handler.py  test_handler.py
backend/lambda/engine/  (skeleton, see M02-T07)
contracts/admin-domains.json  contracts/jobs.json
scripts/deploy/cdk-params.sh  scripts/deploy/deploy-admin-www.sh
.github/workflows/cdk-diff.yml  deploy-backend.yml  deploy-admin-web.yml
docs/architecture/overview.md  security.md
docs/deployment/setup.md  admin-website.md
```

## Invariants this change preserves

- Secret parameters use `noEcho: true`. No secret value in git.
- Every bucket is private, TLS-only, versioned, `RETAIN`.
- The tables are `RETAIN`, encrypted, with point-in-time recovery.
- Sign-in fails closed: an account that is not on the allow-list gets no
  token.
- Every JWT route's handler also calls `_require_admin`.
- All kill switches default to `false`. `BrokerMode` allows only
  `paper`.
- Schedules use EventBridge Scheduler with an IAM-role target.
- `AdminApiFn` cannot read the broker or model secrets.
- No account id, certificate ARN, email or domain in git.

## Steps

### M02-T01 CDK app scaffold

1. Copy `backend/infrastructure/package.json` (same dependency
   versions, same `overrides` and `allowScripts`), `tsconfig.json`,
   `jest.config.js`, `cdk.json`, and `backend/scripts/run-cdk-app.sh`.
2. Run `npm install` in `backend/infrastructure` and commit
   `package-lock.json`.
3. `bin/app.ts`: copy, keep the tag block and the qualifier block
   exactly:
   ```ts
   const bootstrapQualifier = process.env.CDK_BOOTSTRAP_QUALIFIER;
   if (bootstrapQualifier) {
     app.node.setContext("@aws-cdk/core:bootstrapQualifier", bootstrapQualifier);
   }
   const synthesizer = bootstrapQualifier
     ? new cdk.DefaultStackSynthesizer({ qualifier: bootstrapQualifier })
     : undefined;
   ```
   Create two stacks, `findingalpha` and `findingalpha-admin-web`, both
   with that `synthesizer`. Pass the backend stack's API endpoint to the
   web stack as `cspApiConnectOrigin`. Set `Organization` to `LX Software`
   and `Project` to `Finding Alpha` on both stacks.
4. Never pass `--qualifier` to `cdk deploy` or `cdk diff`. That flag is
   for `cdk bootstrap` only. The environment variable is the mechanism.
5. Remove the M01 guards from the `lint-cdk` and
   `test-infrastructure` CI jobs.
6. Check: `CDK_SKIP_PYTHON_PIP=1 npx cdk synth --quiet` lists both
   stacks (after the later steps).

### M02-T02 Shared constructs

Copy `lib/constructs/python-lambda.ts` and
`lib/constructs/checkov-suppressions.ts` unchanged. Copy
`test/python-lambda.test.ts`. Do not copy `siutindei-data-api.ts`.

### M02-T03 Parameters

`lib/parameters.ts`, modelled on `admin-parameters.ts`. One function
`defineParameters(scope: cdk.Stack)` that creates every parameter in
`reference.md` section 3 for the `findingalpha` stack and returns them
in an object. Rules:

- Create parameters on the stack itself so the logical id is the
  parameter name.
- `noEcho: true` on `GoogleClientSecret` and
  `AdminBootstrapTempPassword`.
- Kill switches: `type: "String"`, `allowedValues: ["true", "false"]`,
  `default: "false"`.
- `BrokerMode`: `allowedValues: ["paper"]`, `default: "paper"`.
- `AdminWebDomainName` has no default. The sibling takes its default
  from `contracts/admin-domains.json`. Here the domain is not known, so
  the deploy workflow always passes it.

`contracts/admin-domains.json` holds only what is known now:

```json
{ "storageKeyPrefix": "fa_admin", "cognitoDomainPrefix": "findingalpha-admin-auth" }
```

Extend `scripts/sync-contracts.py` to write
`backend/infrastructure/lib/shared-contracts.ts` exporting those two
constants.

### M02-T04 Encryption, tables, buckets

`lib/data.ts`, modelled on `admin-data.ts`. Three functions:

1. `defineSharedEncryption(scope)`: one KMS key, alias
   `findingalpha/shared`, rotation on, `RETAIN`, with the key-policy
   statement that lets CloudWatch Logs use it (copy it). One SQS
   dead-letter queue encrypted with the key.
2. `defineTables(scope, key)`: `RecordsTable` (`findingalpha-records`)
   with `pk`, `sk`, index `gsi1` (`gsi1pk`, `gsi1sk`, projection ALL),
   `PAY_PER_REQUEST`, point-in-time recovery, TTL attribute
   `expiresAt`, customer-managed encryption with the key, `RETAIN`.
   `AuditLogTable` (`findingalpha-audit-log`) with `pk`, `sk`, same
   settings, no index.
3. `defineBuckets(scope)`: `AccessLogsBucket`, `DataBucket`, `KbBucket`
   with the names in `reference.md` section 2. All: `S3_MANAGED`
   encryption, `BLOCK_ALL`, `enforceSSL`, versioned, `RETAIN`, server
   access logs to the access-logs bucket under a prefix per bucket.
   Lifecycle: access logs expire after 90 days. On `DataBucket`,
   noncurrent versions expire after 30 days. `KbBucket` has no
   lifecycle rule.

S3-managed encryption is deliberate on the knowledge base bucket: the
Bedrock service role then needs no KMS grant.

### M02-T05 Sign-in gate Lambda

Copy `backend/lambda/pre_token_generation/handler.py` and its tests
unchanged. It is one function for two Cognito triggers and it fails
closed:

- First Google sign-in (`PreSignUp_ExternalProvider`): raises unless the
  email is in `ADMIN_EMAIL_ALLOWLIST`.
- Token generation: raises unless the email is on the list or the user
  already has the `admin` group (the bootstrap user). A match gets the
  `admin` group in the token.

Test emails in the copied tests must use `example.com`.

### M02-T06 Auth construct

Copy `lib/constructs/auth.ts`. Change only names: user pool name and
client name prefix `findingalpha-admin`. Everything else stays:

- User pool: no self sign-up, email sign-in, MFA required with TOTP
  only, password policy of 14+ characters, `RETAIN`.
- The gate Lambda on both `PRE_SIGN_UP` and `PRE_TOKEN_GENERATION`.
- Google identity provider with the secret from the `noEcho` parameter.
- App client without a secret, authorization-code grant, scopes
  `openid email profile`, callback
  `https://<AdminWebDomainName>/auth/callback`, logout
  `https://<AdminWebDomainName>/`, token revocation on, user-existence
  errors hidden.
- Hosted UI on the prefix domain, or on the custom domain when both
  custom-domain parameters are set.
- Group `admin`, precedence 1.
- Bootstrap user through the three chained custom resources.

Start with the prefix domain. The custom domain `auth.<domain>` is
optional and needs the parent domain to resolve in DNS first.

### M02-T07 Engine Lambda skeleton

Create `backend/lambda/engine/` with these files. Copy the named
sibling files from `backend/lambda/admin/` and trim.

| File | Source | Content |
| --- | --- | --- |
| `runtime.py` | `runtime.py` | Logger, lazy boto clients, `ADMIN_GROUP = "admin"` |
| `config.py` | `config.py` | Environment accessors, `flag_value`, `env_flag`. Read the environment on each call |
| `timeutil.py` | `timeutil.py` | UTC helpers |
| `http_common.py` | `http_common.py` | `_json_response`, `_claims`, `_groups_include_admin`, `_require_admin`, `_route`, `_request_id`, `_parse_json_body`, `_log_event`, cursor helpers. Drop the public-API and upload helpers |
| `audit.py` | `_audit` in `http_common.py` | Write one audit row |
| `router.py` | `router.py` | `Route`, `route_matches` |
| `store.py` | new | `get(pk, sk)`, `put(item)`, `query_pk(pk, prefix)`, `query_gsi1(gsi1pk, ...)`, `update(...)`, all on `RECORDS_TABLE_NAME` |
| `kill_switch.py` | new | `is_enabled(name)`. See below |
| `job_runs.py` | new | `record(job)` context manager. See below |
| `api_handler.py` | `dispatch.py` pattern | `lambda_handler` with a route table: `GET /health`, `GET /me` |
| `jobs_handler.py` | `dispatch.py` internal pattern | `lambda_handler` with a job table: `noop`, `tick` |
| `requirements.txt` | new | Empty. boto3 is in the runtime |

`kill_switch.is_enabled(name)` returns true only when **both** the
environment flag (the stack parameter) and the runtime setting
`SETTINGS#global` / `META` attribute of the same name are true. A
missing variable, a missing row, a read error: false. Log one line
with the tag `kill_switch` when the answer is false.

`job_runs.record(job)` writes a `JOB#<job>` / `RUN#<startIso>` row with
status `running`, then `succeeded`, `failed` (with the error class and
a short message, no stack trace) or `skipped_disabled`. It sets
`gsi1pk = JOBRUNS` and `expiresAt` 400 days ahead.

`jobs_handler.lambda_handler(event, context)`:

```python
def lambda_handler(event, context):
    job = str((event or {}).get("job") or "")
    handler = JOBS.get(job)
    if handler is None:
        _log_event("error", tag="unknown_job", job=job)
        return {"ok": False, "error": "unknown job"}
    with job_runs.record(job) as run:
        return handler(event, run)
```

`/me` returns only `sub`, `email` and the groups from the claims.
`_require_admin` failure returns 403 with `{"message": "Forbidden"}`.

Tests (write first): `test_http_common.py` (the bracketed
`"[admin]"` groups form and the list form), `test_kill_switch.py`
(every missing-piece case is false), `test_job_runs.py`,
`test_api_handler.py`, `test_jobs_handler.py`. Stub boto3 the way the
sibling tests do.

### M02-T08 Secrets and functions

`lib/secrets.ts`: two `secretsmanager.Secret` resources named
`findingalpha/alpaca-paper` and `findingalpha/openrouter`, encrypted
with the shared key, `RETAIN`, no generated value the code would
accept (the code treats a secret without the expected JSON fields as
"not configured").

`lib/functions.ts`, modelled on `admin-api-function.ts` and
`admin-api-authorizers.ts`:

1. `AdminApiFn` and `EngineFn` through `createPythonLambda` with the
   same `entryDir` and the handlers, timeouts and memory in
   `reference.md` section 4. Both get the shared key for environment
   and logs and the dead-letter queue.
2. Environment variables from `reference.md` section 4. Pass secret
   **names as literals** (`"findingalpha/alpaca-paper"`). Do not use
   `secret.secretName`: it parses the ARN and cuts the name at the
   first hyphen.
3. Grants: `RecordsTable` read/write to both. `AuditLogTable` write to
   `AdminApiFn`. `DataBucket` read to `AdminApiFn`, read/write to
   `EngineFn`. `KbBucket` read/write to `EngineFn`. The two secrets
   read to `EngineFn` only. `engineFn.grantInvoke(adminFn)`.
4. `new lambda.EventInvokeConfig` on `EngineFn` with
   `retryAttempts: 0` and `maxEventAge` 10 minutes. A failed money job
   must not run twice by itself.
5. JWT authorizer: issuer
   `https://cognito-idp.<region>.amazonaws.com/<userPoolId>`,
   `jwtAudience` the app client id. The SPA sends the **ID token**.

### M02-T09 HTTP API

`lib/api-routes.ts`: copy the `AdminApiRoute` type and a `ROUTES`
array with `GET /health` (auth `none`) first and `GET /me` (auth
`jwt`). Later milestones append routes here.

`lib/http-api.ts`: copy `admin-http-api.ts` and trim:

- Keep `SharedPermissionLambdaIntegration` and the single
  `AdminApiInvoke` permission.
- CORS: one origin, `https://<AdminWebDomainName>`. Headers
  `authorization`, `content-type`. Methods GET, POST, PUT, OPTIONS.
  `allowCredentials: false`.
- Keep the encrypted access log group and the access log format.
- Keep the stage throttle (50 a second, burst 100).
- Remove the public-origin condition, the API-key authorizer and the
  `PUBLIC_API_BASE_URL` block.

### M02-T10 Schedules and alarms

`contracts/jobs.json` lists every job in `reference.md` section 9 with
its schedule name, cron, time zone, kill switch and whether a manual
run is allowed. In this milestone `lib/schedules.ts` creates only
`findingalpha-tick` (`rate(15 minutes)`, payload `{"job": "tick"}`,
`retryAttempts: 0`), using `scheduler.Schedule` with
`schedulerTargets.LambdaInvoke(engineFn, ...)` as in
`board-schedules.ts`. `tick` does nothing yet.

`lib/alarms.ts`: an errors alarm on each function (one error in 15
minutes), and an alarm on the dead-letter queue having any visible
message. No alarm actions yet. M11 surfaces alarm state on the
dashboard and in the brief.

### M02-T11 Outputs

`lib/outputs.ts`. Outputs with export names `findingalpha-<Key>`:
`UserPoolId`, `UserPoolClientId`, `CognitoDomain` (full `https://`
origin), `AdminApiBaseUrl`, `RecordsTableName`, `DataBucketName`,
`KbBucketName`, `EngineFunctionName`. The web deploy reads the first
four names exactly as written.

### M02-T12 Stacks

`lib/findingalpha-stack.ts`: modelled on `lxsoftware-stack.ts`. The
constructor calls the functions above in this order: parameters,
encryption, auth, tables, buckets, secrets, functions, HTTP API,
schedules, alarms, outputs. Resources are created by stack-scoped
functions so logical ids stay flat. Do not turn on CDK feature flags.

`lib/findingalpha-admin-web-stack.ts`: copy
`lxsoftware-admin-web-stack.ts` and change:

- `resourcePrefix = "findingalpha"`, bucket names from `reference.md`.
- `AdminWebDomainName` has no default.
- Remove the `cspAssetsConnectOrigins` prop and its place in the
  Content-Security-Policy. The dashboard uploads nothing.
- Export names `findingalpha-admin-web-<Key>`.
- Keep: private bucket with origin access control, the SPA rewrite
  function, the 404-to-`/index.html` response, the security headers
  policy, the optional WAF condition, the bucket-policy `Sid`
  override, logging.

### M02-T13 Stack tests

Jest tests with `aws-cdk-lib/assertions`, modelled on the sibling
tests. Assert at least:

- Both tables: key schema, billing mode, point-in-time recovery,
  encryption, retain policy.
- Every bucket blocks public access and has a TLS-only policy.
- User pool: MFA `ON`, no self sign-up, both Lambda triggers set.
- App client: no secret, code grant, callback built from the parameter.
- `GoogleClientSecret` and `AdminBootstrapTempPassword` are `NoEcho`.
- Every kill-switch parameter defaults to `false`. `BrokerMode`
  allowed values are exactly `["paper"]`.
- `AdminApiFn`'s role has no statement on either secret. `EngineFn`'s
  role has both.
- Every route except `/health` has the JWT authorizer.
- Exactly one `AWS::Lambda::Permission` for API Gateway on `AdminApiFn`.
- The schedule is an `AWS::Scheduler::Schedule`. No `AWS::Events::Rule`.
- Web stack: one bucket policy, the CSP contains the API origin and the
  Cognito origin, viewer protocol policy redirects to HTTPS.

Check: `npm run build && npm test` in `backend/infrastructure`.

### M02-T14 Parameter file and helper

`backend/infrastructure/params/production.json`: only the "params
file" rows of `reference.md` section 3. Example:

```json
{
  "findingalpha:CognitoDomainPrefix": "findingalpha-admin-auth",
  "findingalpha:IngestEnabled": "false",
  "findingalpha:CommitteeEnabled": "false",
  "findingalpha:TradingEnabled": "false",
  "findingalpha:LeverageEnabled": "false",
  "findingalpha:BriefEmailEnabled": "false",
  "findingalpha:BrokerMode": "paper"
}
```

`scripts/deploy/cdk-params.sh`: copy. Two arrays, `BACKEND_PARAM_ARGS`
(keys starting `findingalpha:`) and `ADMIN_WEB_PARAM_ARGS` (keys
starting `findingalpha-admin-web:`). A key with any other prefix, or
without a prefix, is an error. `params/README.md`: copy and adapt,
without any account id.

### M02-T15 Workflows

`cdk-diff.yml`: copy. It runs on pull requests that touch
`backend/**` or `contracts/**` and posts the diff. Stack names
replaced.

`deploy-backend.yml`: copy. Changes:

- Paths: `backend/infrastructure/**`, `backend/lambda/**`,
  `contracts/**`, `!contracts/roadmap.json`.
- Keep the bootstrap check step as is. With the variable set it checks
  `/cdk-bootstrap/siutindei/version`.
- One deploy command:
  ```bash
  npx cdk deploy --require-approval never \
    "${BACKEND_PARAM_ARGS[@]}" "${ADMIN_WEB_PARAM_ARGS[@]}" \
    --parameters "findingalpha:AdminWebDomainName=${P_ADMIN_DOMAIN}" \
    --parameters "findingalpha:GoogleClientId=${P_GOOGLE_CLIENT_ID}" \
    --parameters "findingalpha:GoogleClientSecret=${P_GOOGLE_CLIENT_SECRET}" \
    --parameters "findingalpha:AdminFederatedEmailAllowlist=${P_EMAIL_ALLOWLIST}" \
    --parameters "findingalpha:AdminBootstrapEmail=${P_BOOTSTRAP_EMAIL}" \
    --parameters "findingalpha:AdminBootstrapTempPassword=${P_BOOTSTRAP_PASSWORD}" \
    --parameters "findingalpha:MailSendingDomain=${P_MAIL_DOMAIN}" \
    --parameters "findingalpha:BriefRecipientEmail=${P_BRIEF_RECIPIENT}" \
    --parameters "findingalpha:SecContactEmail=${P_SEC_CONTACT}" \
    --parameters "findingalpha-admin-web:AdminWebDomainName=${P_ADMIN_DOMAIN}" \
    --parameters "findingalpha-admin-web:AdminWebCertificateArn=${P_CERT_ARN}" \
    --parameters "findingalpha-admin-web:CspCognitoConnectOrigin=${P_COGNITO_ORIGIN}" \
    --parameters "findingalpha-admin-web:WafWebAclArn=${P_WAF_ARN}" \
    findingalpha findingalpha-admin-web
  ```
  with each `P_*` taken from the GitHub variable or secret in
  `reference.md` section 3. Add a first step that fails with a clear
  message when `ADMIN_WEB_DOMAIN_NAME` or `ADMIN_WEB_CERTIFICATE_ARN`
  is empty.
- Do not use `--exclusively`.

`deploy-admin-web.yml` and `scripts/deploy/deploy-admin-www.sh`: copy.
Changes: stack name `findingalpha`, web stack `findingalpha-admin-web`,
`VITE_COGNITO_REDIRECT_URI: https://${{ vars.ADMIN_WEB_DOMAIN_NAME }}/auth/callback`,
`VITE_COGNITO_LOGOUT_URI: https://${{ vars.ADMIN_WEB_DOMAIN_NAME }}/`,
and add `contracts/roadmap.json` to the push paths. The workflow has
nothing to build until M03. Add it in M03 if that is simpler to
review.

All deploy jobs use `environment: production`.

### M02-T16 Documents

- `docs/deployment/setup.md`: copy the sections on OIDC, the role,
  bootstrap and the GitHub environment. State that the bootstrap with
  qualifier `siutindei` is reused and no bootstrap workflow exists
  here.
- `docs/deployment/admin-website.md`: copy the pre-deploy checklist,
  sections 1 to 5, "Auditing admin sign-ins" and "Local UI without a
  stack". Replace names. Write hostnames as `admin.<domain>`.
- `docs/architecture/overview.md` and `security.md`: short, from
  `00-overview.md` sections 3 and 4.

### M02-T17 First deploy and smoke test

Needs owner tasks O01, O04, O05, O06, O07 done.

1. Merge. **Deploy Backend** runs. If it fails at the bootstrap check,
   stop and tell the owner (O05).
2. The developer adds the `admin` DNS record in Cloudflare after the
   owner's go (O08). The owner adds the Google redirect URI (O07).
3. Smoke test, from the sibling runbook:
   - `GET <AdminApiBaseUrl>/health` returns 200 without a token.
   - `GET /me` without a token returns 401.
   - The Scheduler console shows `findingalpha-tick` and the records
     table gets `JOB#tick` run rows.
   - Both secrets exist. Do not read their values.
   - Sign-in itself is tested in M03 when there is a page to sign in to.

### Fallback: backend before the certificate

If the certificate is late and the owner wants ingest (M04) running
first,
the `findingalpha` stack can deploy alone. The domain is only used for
the Cognito callback and CORS, and CDK rewrites both on the next
deploy. This needs the owner's explicit yes, a placeholder value in
the GitHub variable, and a temporary edit of the deploy command to name
only `findingalpha`. Do not do it by default.

## Done when

- `npm run build` and `npm test` pass in `backend/infrastructure`.
- `python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
  and the same for `pre_token_generation` pass.
- `cdk-diff` on the pull request shows only creations.
- Checkov in `security.yml` passes, with suppressions only from the
  copied aspect.
- After merge: both stacks are `CREATE_COMPLETE` and the smoke test in
  T17 passes. Paste the workflow run link in the pull request.

## Rollback

Before the first deploy: revert. After: revert the pull request and
let the deploy run. Buckets, tables, the key and the user pool are
`RETAIN` and stay. Do not delete them by hand. A stack stuck in
`UPDATE_ROLLBACK_FAILED` is handled as the sibling runbook describes,
by the owner.

## Open questions

- Can an existing global WAF web ACL be shared (variable
  `ADMIN_WAF_WEB_ACL_ARN`)? Empty is acceptable.
- Does `GitHubActionsRole` already cover `findingalpha*` resource
  names? (Owner task O05.)
