# Security

The rules in [`overview.md`](overview.md) are the product rules. This
page is how the skeleton enforces them.

## Secrets and personal data

Nothing in git identifies the owner: no account id, certificate ARN,
email or domain. The dashboard hostname is the parameter
`AdminWebDomainName`, written in docs as `admin.<domain>`.

`GoogleClientSecret` is a CloudFormation parameter with `noEcho: true`.
Broker and model keys are Secrets
Manager secrets named `findingalpha/alpaca-paper` and
`findingalpha/openrouter`, encrypted with the shared key and retained.
The Lambda environment receives those names as string literals. A secret
that lacks the JSON fields the engine expects counts as not configured.

`AdminApiFn` cannot read either secret. `EngineFn` can read both.

## Sign-in

The user pool does not allow self sign-up and does not enrol an
authenticator app. Sign-in is Google only. The same Lambda is the Pre
Sign-up and Pre Token Generation trigger. An email that is not on the
allow-list and is not already in the `admin` group receives no token.
The app client has no secret, offers no password flow, uses the
authorization-code grant, and builds its callback from
`AdminWebDomainName`. If Google sign-in breaks, revert the change that
removed the password client; the old password user stays in the pool
until it is deleted in the Cognito console.

## Data

Buckets are private (`BLOCK_ALL`), TLS-only, versioned and `RETAIN`.
Tables are `RETAIN`, encrypted with the customer-managed key, and have
point-in-time recovery. The key rotates and is retained. Schedules are
EventBridge Scheduler with an IAM-role target. There is no
`AWS::Events::Rule`. A failed async invoke of `EngineFn` is not retried.

Kill switches are strings `true` or `false` and default to `false`.
`BrokerMode` allows only `paper`.

## API keys

`/v1/partner/*` uses a Lambda authorizer, not the dashboard JWT. The
caller sends `Authorization: Bearer <token>`. The authorizer reads one
`APIKEY#*` row and may update `lastUsedAt` on that row. It cannot scan
the table. The plaintext token is shown once, at mint time, and only
its scrypt digest is stored. Logs carry the first eight hex characters
of the digest.

The authorizer cache is 60 seconds and does not include the HTTP
method, so the authorizer never denies a method. The Manage Public
API Keys workflow replaces scopes with `set-scopes`. The caller
repeats every scope the key should keep. A scope that tier cannot
hold is refused. The write flag is a separate `set-write`. The engine allows a write only when the key has
`operate`, the key's `allowWrite` flag is on, and
`PublicApiWritesEnabled` is `true`. A key can turn a switch off. It
cannot turn one on. A denied read is 404. A denied write is 403 with
a reason. Dashboard routes ignore a token, and a dashboard token is
ignored on `/v1/partner`.

CORS stays the dashboard origin. Key callers are servers and do not
send a browser preflight. `GET /api-keys` is the dashboard list and
never returns the digest. No key can read it.

## Edge

The HTTP API allows one browser origin, `https://` plus
`AdminWebDomainName`. Credentials are not allowed on CORS. The stage
throttles at 50 requests a second with a burst of 100. API Gateway has
one invoke permission on `AdminApiFn`.

The dashboard distribution redirects viewers to HTTPS. Its
content-security policy allows the API origin and the Cognito origin(s)
passed as `CspCognitoConnectOrigin` (the prefix URL, and when the custom
domain is set also `https://auth.<domain>`). A web ACL is attached only
when `WafWebAclArn` is set.

## Branch protection

`main` is gated by an active ruleset on `refs/heads/main`. The ruleset
blocks deletion and force-push, and requires status checks whose
contexts match a job name in `.github/workflows`. The aggregator jobs
are `lint`, `test`, and `security-summary`.

The weekly **Verify GitHub Rulesets** workflow calls
`lx-software-ltd/actions/verify-rulesets` at
`a1816561097c19870cc3a4af1407b6ac2caddfe6`. It fails unless the
approving-review count is exactly 0 and the required checks are exactly
`lint`, `test`, and `security-summary`. A ruleset that targets `main`
while its enforcement is not `active` fails that job. A required
context with no matching job name fails it too.

Release tags `v*` need an active ruleset, or classic tag protection.
