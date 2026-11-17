# Plan: M03A external API with keys and scopes

**Status**: Done. The live checks passed: health, a system key's route list, a refused write, and the dashboard. The `api` record is DNS only. Writes stay off.
**Zone**: red (authorizer Lambda, CDK routes and IAM, a contract, a
workflow)

## Goal

Other systems (scripts, monitors, other agents) can read and operate
findingalpha over HTTPS with an API key, without a browser sign-in.
Keys have a **tier** and **scopes**. Two tiers are defined, `admin`
and `user`. Only `admin` is built. A `user` key cannot be minted and
is refused if one ever appears in the table.

This is the `lx-software` "public API key" design, copied: `/public/*`
mirror routes, the `x-api-key` header, a Lambda authorizer, scrypt
digests, scopes, expiry, an optional IP allow-list, a write flag, a
stack kill switch for writes, and owner-only routes that no key can
reach. The additions are the tier, a route index, and the hostname
`api.<domain>`, which follows the custom-domain pattern of the
`siutindei` API stack.

## Non-goals

- No `user` tier behaviour. Only its name and its place in the
  contract.
- No key management in the dashboard. Keys are minted and revoked by
  the script and the GitHub workflow, as in the sibling. The dashboard
  only lists them.
- No OAuth client-credentials flow, no JWT for machines, no per-key
  rate plans.
- No edge caching, no Cloudflare proxy and no second hostname for the
  API.
- The dashboard does not move to `api.<domain>`. It keeps calling the
  `AdminApiBaseUrl` address, so the default API Gateway endpoint stays
  enabled.
- No route that exists only for keys, except the index.

## How it works

1. A caller sends `x-api-key: fapk_...` to
   `https://api.<domain>/public/<path>`, where `<path>` is the path of
   a dashboard route. Example:
   `GET https://api.<domain>/public/system/status`. The same routes
   also answer on the `AdminApiBaseUrl` address.
2. API Gateway calls `PublicApiKeyAuthorizerFn`. It computes the
   scrypt digest of the key, reads `APIKEY#<digest>` / `META`, and
   denies when the row is missing, revoked, expired, of a tier that is
   not enabled, without scopes, or called from an address outside its
   allow-list. On allow it passes `keyId`, `label`, `tier`, `scopes`
   and `write` to the handler. The verdict is cached 60 seconds per
   key and source address.
3. `AdminApiFn` strips `/public`, finds the route in the same route
   table the dashboard uses, and checks the route's scope against the
   key. It then runs the same handler function the dashboard route
   runs.
4. A write (`PUT`, `POST`) needs all of: the stack parameter
   `PublicApiWritesEnabled` is `true`, the key has `allowWrite`, the
   key has the scope `operate`, and the route is not owner-only.

## Tiers and scopes

`contracts/public-api-scopes.json`:

```json
{
  "scopes": [
    { "name": "SCOPE_SYSTEM", "value": "system" },
    { "name": "SCOPE_RESEARCH", "value": "research" },
    { "name": "SCOPE_PORTFOLIO", "value": "portfolio" },
    { "name": "SCOPE_OPERATE", "value": "operate" }
  ],
  "tiers": [
    {
      "name": "TIER_ADMIN",
      "value": "admin",
      "enabled": true,
      "scopes": ["system", "research", "portfolio", "operate"],
      "mayWrite": true
    },
    {
      "name": "TIER_USER",
      "value": "user",
      "enabled": false,
      "scopes": ["research"],
      "mayWrite": false
    }
  ]
}
```

| Scope | Gives |
| --- | --- |
| `system` | Status, switches, job runs, owner tasks, costs, breakers, gate. Read only |
| `research` | Universe, methodology, screens, backtests, knowledge base status, committee runs, theses, proposals. Read only |
| `portfolio` | Portfolio, ledger, holds, briefs. Read only. Contains money amounts |
| `operate` | The writes in the table below |

A key holds one tier and a subset of that tier's scopes. The scope of
each route is in `reference.md` section 8.

Writes a key with `operate` may do:

| Write | Limit |
| --- | --- |
| `PUT /public/settings` | Only to turn switches **off**. A body that sets any switch to `true` is refused |
| `POST /public/jobs/{jobName}/run` | Only jobs marked `keyRun: true` in `contracts/jobs.json`. Every job is marked |
| `POST /public/kb/sync` | Same caps as from the dashboard |
| `POST /public/holds/{holdId}/veto` | Same rules as from the dashboard |

Owner-only, never reachable with any key, whatever its tier:

- turning any switch on;
- `POST /breakers/{name}/reset`;
- `PUT /owner-tasks/{taskId}`;
- `GET /api-keys` and anything that manages keys;
- `GET /me`;
- every approval of a real-money order (M12).

The reason is the same as in the sibling: a leaked key must not be
able to turn a switch on, clear an alarm, or widen its own access.
A key with `operate` and writes enabled can start every job, including
broker jobs and drills. Each job still checks its own kill switch.
The production parameter file later sets `PublicApiWritesEnabled` to
`true`. The parameter default stays `false`, and this owner-only list
does not change.

## Files

```
contracts/public-api-scopes.json   contracts/jobs.json (keyRun)   (red)
backend/lambda/public_api_authorizer/{handler,api_key_hash,api_key_scopes,public_api_scopes_generated,test_handler}.py
backend/lambda/public_api_authorizer/requirements.txt
backend/lambda/engine/public_api.py   test_public_api.py
backend/lambda/engine/router.py  api_handler.py  http_common.py  audit.py
backend/infrastructure/lib/authorizers.ts  api-routes.ts  parameters.ts  functions.ts   (red)
backend/infrastructure/test/*.test.ts
scripts/manage-public-api-keys.py   scripts/test_manage_public_api_keys.py
scripts/sync-contracts.py   scripts/check-contracts.py
.github/workflows/manage-api-keys.yml   .gitleaks.toml
apps/admin_web/src/pages/SystemPage.tsx   (+ mock, test)
docs/architecture/security.md   docs/deployment/admin-website.md
```

## Invariants this change preserves

- The plaintext key exists once, at mint time. Only its scrypt digest
  is stored or logged.
- Every denial path in the authorizer returns `isAuthorized: false`,
  including a table error and an unparseable expiry.
- A route without a `key_scope` is not reachable with a key.
- `PublicApiWritesEnabled` defaults to `false`.
- The authorizer never decides on the HTTP method, because its cache
  key has no method. The handler enforces writes.
- The authorizer function can read and update only `APIKEY#*` rows.
- Every write by a key is audited as `USER#apikey:<keyId>`.
- Dashboard routes keep the Cognito authorizer and `_require_admin`.
  A key never works on them.

## Steps

### M03A-T01 Contract

1. Add `contracts/public-api-scopes.json` as above.
2. `scripts/sync-contracts.py`: generate
   `backend/lambda/public_api_authorizer/public_api_scopes_generated.py`
   (`ALL_SCOPES`, one constant per scope, `TIERS` as a dict of value to
   `{enabled, scopes, mayWrite}`), and add the same constants to
   `backend/lambda/engine/contract_constants.py`. The sibling script
   does this for its scopes file. Port that block. There is no
   `legacyReadScope` here.
3. `scripts/check-contracts.py`: every tier scope is a known scope; a
   tier with `mayWrite: false` does not list `operate`.
4. `contracts/jobs.json`: add `keyRun` (boolean, default `false`) to
   every job. Set it `true` only for jobs that neither trade nor touch
   the broker or the drill: for now `tick`. Later milestones set it
   when they add a job, and say so in their pull request.

### M03A-T02 Authorizer Lambda

Copy `backend/lambda/public_api_authorizer/` from `lx-software`.
Changes:

- `api_key_hash.py`: salt `b"findingalpha-public-api-key-v1"`. Keep
  the scrypt parameters and the comment that explains them.
- `api_key_scopes.py`: remove the legacy `scope=read` branch. Add
  `key_tier(item)` and `tier_allows(item)`: the row's `tier` must be a
  tier whose `enabled` is true, and `normalize_scopes` keeps only the
  scopes that tier lists. `key_allows_write` also requires the tier's
  `mayWrite`.
- `handler.py`: after the expiry check, deny with reason `tier` when
  `tier_allows` is false. Add `tier` to the context. Remove
  `_enqueue_denied_notify` and its calls for now (M11 adds alerts).
  Keep everything else: the 256-character limit, `_is_expired` failing
  closed, the 60-second `lastUsedAt` throttle, the structured log
  lines with `digest_prefix` only.

Add the folder to the Python test job in `test.yml` and to the
`verify-change` skill, beside `pre_token_generation`.

Tests: copy `test_handler.py` and adapt. Add: a row with tier `user`
is denied; a row without a tier is denied; a scope outside the tier is
dropped; `allowWrite` on a tier that may not write gives `write: "0"`.

### M03A-T03 Infrastructure (red: ask first)

Copy the key half of `admin-api-authorizers.ts` into
`lib/authorizers.ts`, beside the Cognito authorizer from M02:

- `PublicApiKeyAuthorizerFn`: `createPythonLambda`, timeout 5 s,
  memory 256 MB, environment `RECORDS_TABLE_NAME`, shared key, shared
  dead-letter queue.
- The narrow policy: `dynamodb:GetItem` and `dynamodb:UpdateItem` on
  the records table with the condition
  `ForAllValues:StringLike dynamodb:LeadingKeys = ["APIKEY#*"]`, and
  `grantDecrypt` on the shared key.
- `HttpLambdaAuthorizer("public-api-key", ...)`: simple responses,
  identity sources `$request.header.x-api-key` and
  `$context.identity.sourceIp`, cache 60 seconds.

Parameter `PublicApiWritesEnabled` (`true` or `false`, default
`false`) and the environment variable `PUBLIC_API_WRITES_ENABLED` on
`AdminApiFn`.

Routes, with the sibling's throttles:

| Route | Authorizer | Throttle |
| --- | --- | --- |
| `GET /public` | key | 2 a second, burst 10 |
| `GET /public/{proxy+}` | key | 2 a second, burst 10 |
| `PUT /public/{proxy+}`, `POST /public/{proxy+}` | key | 1 a second, burst 5 |
| `GET /api-keys` | Cognito | default |

One proxy route serves every mirror, so a later milestone that adds a
mirrored route changes no infrastructure. The handler's route table is
the allow-list.

Custom hostname, after the `siutindei` API stack (`ApiCustomDomain`
there is for a REST API. This one is the HTTP API equivalent):

- Parameters `ApiCustomDomainName` and `ApiCustomDomainCertificateArn`,
  both default empty. Values come from the GitHub variables
  `API_CUSTOM_DOMAIN_NAME` and `API_CUSTOM_DOMAIN_CERTIFICATE_ARN`. Add
  both to the deploy command in `deploy-backend.yml`.
- Condition `UseApiCustomDomain`: both parameters are not empty. With
  either one empty the stack creates no domain and deploys as before.
- `apigwv2.DomainName` with the imported certificate, a regional
  endpoint and security policy TLS 1.2, and an `apigwv2.ApiMapping`
  from the domain to the `$default` stage with no path prefix. Put the
  condition on both resources through `cfnOptions.condition`, as the
  sibling does.
- The certificate is in the **stack's region**, not `us-east-1`. A
  regional endpoint cannot use a `us-east-1` certificate.
- Outputs, both conditional: `ApiCustomDomainTarget` (the regional
  name, `d-<id>.execute-api.<region>.amazonaws.com`, which the DNS
  record points at) and `ApiCustomDomainUrl` (`https://api.<domain>`).
- Do not set `disableExecuteApiEndpoint`. The dashboard uses the
  default endpoint.
- CORS does not change. It allows only the dashboard origin. Callers
  with a key are servers, not browsers.

Jest: the authorizer's policy has the leading-key condition and no
other table action; the proxy routes use the key authorizer; no
dashboard route uses it; the parameter defaults to `false`;
`AdminApiFn` has no new permission; with both domain parameters empty
the template has the domain and the mapping only under the condition;
the domain is regional with TLS 1.2.

### M03A-T04 Engine

1. `router.py`: each `Route` gets two fields: `key_scope` (a scope
   value, or `None` for "not mirrored") and `key_write` (`False` by
   default; `True` only for the four writes listed above). Fill them
   for the M02 and M03 routes from `reference.md` section 8.
2. `public_api.py`, a small port of the sibling's
   `board_public_api.py`:
   - `key_context(event)`: reads
     `requestContext.authorizer.lambda`.
   - `scopes_from_key_context`, `key_context_allows_write`,
     `writes_enabled` as in the sibling.
   - `resolve(method, path)`: strips `/public`, returns the matching
     `Route` or `None`.
   - `deny_reason(method, route, key_ctx)`: `not_mirrored`, `scope`,
     `writes_disabled`, `key_read_only`, `owner_only`, or `None`. A
     PUT, POST or DELETE on a route that is not `key_write` is
     `owner_only` even when the key holds that route's scope.
   - `settings_body_allowed(body)`: true only when every value is
     `false`.
   - `route_index(key_ctx)`: the mirrored routes the key may call,
     with method, path, scope and whether it is a write.
3. `api_handler.py`: a request whose path starts with `/public` goes
   to `public_api.handle`. It never calls `_require_admin`. Any other
   path never looks at the key context. Responses as in the sibling: a
   denied read returns 404, a denied write returns 403 with
   `{"message": "Forbidden", "reason": "<reason>"}`.
4. Handlers receive an `actor`: the Cognito `sub` from the dashboard,
   `apikey:<keyId>` from a key. `audit.write` uses it. The dashboard
   partition key stays `USER#<sub>`.
5. `GET /public` returns `route_index`.
6. `GET /api-keys` (Cognito only): query `gsi1pk = APIKEYS` and return
   `keyId`, `label`, `tier`, `scopes`, `allowWrite`, `revoked`,
   `createdAt`, `expiresAt`, `lastUsedAt`, `allowedCidrs`. Never the
   digest.

Tests: every route in the table is either mirrored with a scope or
explicitly not mirrored (a route added without deciding fails the
test); a key without the scope gets 404; each write reason; a settings
body with one `true` is refused; a key context on a dashboard path is
ignored; the dashboard JWT on a `/public` path is refused; the index
lists only what the key may call.

### M03A-T05 Key management

Copy `scripts/manage-public-api-keys.py`. Changes: prefix `fapk_`,
default table `findingalpha-records`, default scopes `system`, a
`--tier` argument whose only accepted value is `admin` (the script
exits with "tier user is not built yet" for `user`), the tier written
on the row, and the example lines.

Copy `.github/workflows/manage-api-keys.yml` unchanged apart from
names and a `tier` input. It needs the environment secret
`PUBLIC_API_KEY_GPG_PASSPHRASE`, because this repository and its logs
are public: a new key is shown only as a gpg-encrypted block in the
run summary.

`.gitleaks.toml`: copy the sibling file's structure and its rule that
flags a committed key, with the prefix `fapk_`.

`GitHubActionsRole` needs, on the records table, `GetItem`, `PutItem`,
`UpdateItem` and `Scan`, and `kms:Decrypt` and `kms:GenerateDataKey`
on the shared key. That is an account change by the owner (O05).

### M03A-T06 Dashboard

System page: a card "API keys" fed by `GET /api-keys`. Columns: label,
tier, scopes, read or write, created, expires, last used, state
(active, expired, revoked). A line under it: "Keys are created and
revoked with the Manage Public API Keys workflow." A key that expires
within 14 days is highlighted. Mock fixture and a unit test.

### M03A-T07 Documents

- `docs/architecture/security.md`: the "API authorization" paragraph
  on keys, from the sibling, with these names.
- `docs/deployment/admin-website.md`: a "Public API keys" section:
  the scope table, the write rules, the owner-only list, how to mint,
  list, revoke, and decrypt the minted key, and `curl` examples:

  ```bash
  API="https://api.<domain>"
  curl -H "x-api-key: fapk_..." "$API/public"
  curl -H "x-api-key: fapk_..." "$API/public/system/status"
  curl -X PUT -H "x-api-key: fapk_..." -H "Content-Type: application/json" \
    -d '{"tradingEnabled": false}' "$API/public/settings"
  ```
- The same document: a section "API hostname" with the certificate
  region, the two variables, the DNS record, and the warning from the
  `siutindei` consolidation plan: the record must point at the
  `ApiCustomDomainTarget` output, never at the
  `<api-id>.execute-api` name, and must not be proxied.

### M03A-T08 Deploy and test

Needs O19 and O20. Before the numbered tests, bring the hostname up:

- The owner has set the two `API_CUSTOM_DOMAIN_*` variables (O20).
  Deploy.
- With the owner's go, the developer creates the DNS record `api` as a
  CNAME to the `ApiCustomDomainTarget` output, DNS only.
- `curl https://api.<domain>/health` returns 200 with a valid
  certificate. `GET https://api.<domain>/me` without a token returns
  401. The `AdminApiBaseUrl` address still answers and the dashboard
  still works.

Run the tests below against `https://api.<domain>`.

1. With `PublicApiWritesEnabled=false`: mint a key with scope
   `system`. `GET /public` lists the routes. `GET /public/system/status`
   returns 200. `GET /public/settings` returns 200.
   `PUT /public/settings` returns 403 `writes_disabled`. A wrong key
   returns 403. No header returns 401.
2. Revoke the key. Within 60 seconds every call returns 403.
3. Set `PublicApiWritesEnabled=true` and redeploy. Mint a key with
   `system,operate` and `allowWrite`.
   `PUT /public/settings {"ingestEnabled": false}` returns 200 and an
   audit row `USER#apikey:<keyId>` exists.
   `PUT /public/settings {"ingestEnabled": true}` returns 403
   `owner_only`. Revoke the key.

## What later milestones must do

A pull request that adds a dashboard route also sets its `key_scope`
(or leaves it `None` on purpose), updates the table in `reference.md`
section 8, and, for a new job, decides `keyRun`. The test in T04 fails
until this is done.

M11 adds an email alert when a key is denied or is used for a write
(the sibling's "Public API key used" notice).

## Done when

- Unit tests pass in the authorizer folder, the engine and the web
  app. Jest passes.
- The three parts of T08 behaved as written on the deployed stack.
- The System page lists the keys.

## Rollback

Revoke every key with the workflow, then revert the pull request.
Setting `PublicApiWritesEnabled=false` stops all writes by key at
once, without a revert. To remove the hostname: empty the two
`API_CUSTOM_DOMAIN_*` variables, deploy, then delete the `api` DNS
record. In that order, so the record never points at a name that no
longer exists.

## Open questions

- Whether the default API Gateway endpoint should be closed to key
  callers later, so that keys only work on `api.<domain>`. Not
  planned. It would mean moving the dashboard to the hostname first.
- What the `user` tier is for. The contract reserves read-only
  `research`. Decide before building it.
