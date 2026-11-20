# Owner checklist

Things only the owner can do. A developer or agent must not attempt
them and must not ask for secret values in chat. Each item says what it
blocks. The dashboard shows this list with tick boxes from M03.

Values that identify a person or an account go into GitHub Actions
secrets (a repository secret or the `production` environment) or AWS
Secrets Manager. They never go into git, a pull request, or chat.

| Id | Task | Blocks |
| --- | --- | --- |
| O01 | Choose and register the new domain. Add it to Cloudflare DNS. **Done** | First deploy (M02), email (M10) |
| O02 | Protect `main`: pull request required, required checks `lint` and `test`, no force-push | Merging M01 safely |
| O03 | Produce the PII denylist hashes (step in M01) and hand over the hash file | M01 |
| O04 | Create the GitHub variables, the environment `production` and its secrets (list below) | First deploy (M02) |
| O05 | Confirm AWS access for GitHub Actions (details below) | First deploy (M02) |
| O06 | Request an ACM certificate for `admin.<domain>` in `us-east-1` with DNS validation. Give the validation record to the developer, who adds it in Cloudflare (see DNS below). Wait for ISSUED | First deploy (M02) |
| O07 | Create a Google OAuth client (type Web application). Authorised redirect URI: `https://<cognito-domain>/oauth2/idpresponse` | First sign-in (M02) |
| O08 | After the first deploy: say go for the `admin` DNS record. The developer adds it in Cloudflare | Dashboard reachable (M03) |
| O09 | Sign in once with the bootstrap user, set a new password, enrol TOTP | Dashboard use (M03) |
| O10 | Open a free Alpaca paper account. Set the paper balance to the planned capital in US dollars. Store the paper API key in the secret `findingalpha/alpaca-paper` | M04 |
| O11 | Review the provisional formulas listed in M05 and say which to keep | M05 merge |
| O12 | Upload the PDFs to the knowledge base bucket under `theory/`. Split any file over 50 MB | M07 |
| O13 | Write 20 questions whose answers are formulas in the PDFs, with the book and page. Upload as `eval/questions.json` | M07 evaluation |
| O14 | Add `findingalpha` to `contracts/openrouter-apps.json` in `lx-software` (red zone there), mint the key, store it in the secret `findingalpha/openrouter` | M08 |
| O15 | Confirm the tax figures in M09 with an adviser (dividend withholding rate, estate-tax schedule) | M09 register status |
| O16 | Create the sending-domain identity in SES and give the three DKIM records to the developer, who adds them in Cloudflare. Verify the recipient address | M10 |
| O17 | Run the kill-switch and breaker drill with the developer | M11 |
| O18 | Decide on real money after the gate report is green | M12 |
| O19 | Add the secret `PUBLIC_API_KEY_GPG_PASSPHRASE`. Confirm the key-workflow permissions in O05 item 5, then mint the first admin API key with the **Manage Public API Keys** workflow | M03A test |
| O20 | Request an ACM certificate for `api.<domain>` in `ap-southeast-1` (the stack's region, not `us-east-1`) with DNS validation. Give the validation record to the developer. When ISSUED, set the two `API_CUSTOM_DOMAIN_*` variables | API hostname (M03A) |
| O21 | Delete the unused password user in the Cognito console, after Google sign-in works. Sign-in is Google only, with no authenticator-app enrolment | After Google sign-in |

## Details

### O03 PII denylist

The check hashes words and phrases and compares them with a list of
SHA-256 digests, so the list can be public while the values stay
private. The owner runs, on their own machine, for each value to block
(full name, each email, each phone number, home address fragments):

```bash
printf '%s' 'value in lower case' | shasum -a 256
```

and puts one digest per line in `scripts/pii-denylist.sha256`.
Normalisation rules are at the top of `scripts/check_pii.py`: lower
case, apostrophes removed, phone numbers as digits only, names as words
separated by single spaces.

### O04 GitHub variables and secrets

Nothing here is written in git. Values with `<...>` are the owner's.
Do not create a variable or a secret whose value would be empty. An
unset one reads as empty, which is what "optional" means below.

The repository is public, and Actions prints every variable value in
the job log. An email is a secret, so the log shows `***` instead.
The account id is a repository variable on purpose: the first settings
block shows it and later lines are masked, with no warning. The deploy
reads a secret, and the variable of the same name when that secret is
empty. Copy an email variable into the secret, then delete the
variable. Do not paste the value in chat. An empty allow-list, with
neither a secret nor a variable, fails the deploy and does not remove
access.

**Repository variables** (Settings, Secrets and variables, Actions,
Variables). `cdk-diff` on a pull request from this repository can read
these. Until `AWS_ACCOUNT_ID` and `AWS_REGION` are both set, that
check passes with a warning and does not compare the account. A
Dependabot pull request can read the variable.

| Variable | Value |
| --- | --- |
| `AWS_REGION` | `ap-southeast-1` |
| `CDK_BOOTSTRAP_QUALIFIER` | `siutindei` |
| `CDK_PARAM_FILE` | `backend/infrastructure/params/production.json` |
| `AWS_ACCOUNT_ID` | The account id. A repository variable, not a secret |

**Environment `production`, variables.** Needed for the first deploy:

| Variable | Value |
| --- | --- |
| `ADMIN_WEB_DOMAIN_NAME` | `admin.<domain>` |
| `ADMIN_WEB_CERTIFICATE_ARN` | ARN of the issued certificate from O06 |
| `ADMIN_COGNITO_ORIGIN` | `https://findingalpha-admin-auth.auth.ap-southeast-1.amazoncognito.com` |
| `ADMIN_GOOGLE_CLIENT_ID` | From O07 |

Needed later, or optional:

| Variable | Value | When |
| --- | --- | --- |
| `MAIL_SENDING_DOMAIN` | `<domain>` | M10 |
| `API_CUSTOM_DOMAIN_NAME` | `api.<domain>` | M03A |
| `API_CUSTOM_DOMAIN_CERTIFICATE_ARN` | ARN of the issued certificate from O20, in `ap-southeast-1` | M03A |
| `ADMIN_WAF_WEB_ACL_ARN` | ARN of an existing global web ACL | Optional |
| `ADMIN_COGNITO_CUSTOM_DOMAIN_CERTIFICATE_ARN` | Only if sign-in should run on `auth.<domain>` | Optional |

**Environment `production`, secrets:**

| Secret | Value | When |
| --- | --- | --- |
| `ADMIN_GOOGLE_CLIENT_SECRET` | From O07 | First deploy |
| `ADMIN_FEDERATED_EMAIL_ALLOWLIST` | The Google account emails allowed to sign in, lower case, comma-separated. The variable is used until this secret exists | First deploy |
| `SEC_CONTACT_EMAIL` | Contact address sent to the SEC in the `User-Agent` | M04 |
| `BRIEF_RECIPIENT_EMAIL` | Where the daily email goes | M10 |
| `PUBLIC_API_KEY_GPG_PASSPHRASE` | A long random passphrase. Encrypts a newly minted API key in the public run summary | M03A |

Environment settings: limit deployment branches to `main`. The deploy
workflows also refuse any ref other than `main`.

**Not on GitHub:** AWS access keys (the workflows use OIDC and
`GitHubActionsRole`), the Alpaca keys and the OpenRouter key (Secrets
Manager, O10 and O14), and the Cloudflare token (the developer's
environment only).

### DNS records

DNS for `<domain>` is on Cloudflare. The developer creates records
through the Cloudflare API with a token from their environment. Rules:

- only in this project's zone, even if the token can see other zones;
- every record is DNS only (proxy off), except the public `www`
  redirect host below;
- each record is created after the owner says go in chat and is listed
  in the pull request or the chat message;
- the token is never written to git, to GitHub, or to a log.

| Record | Type | Points at | When |
| --- | --- | --- | --- |
| ACM validation name for `admin.<domain>` | CNAME | The validation value ACM shows | Before the first deploy (O06) |
| `admin` | CNAME | The `AdminWebDistributionDomain` output of the `findingalpha-admin-web` stack | After the first deploy (O08) |
| ACM validation name for the public hostname | CNAME | The validation value ACM shows | Before the public www stack deploy |
| Apex (when it is the public hostname) | CNAME | The `PublicWebsiteDistributionDomain` output of the `findingalpha-public-www` stack (Cloudflare flattens the apex) | After the public www stack deploy, owner go |
| `www` | Worker custom domain + Single Redirect | 301 to `https://<domain>` keeping path and query (proxied `AAAA 100::`) | Same go; www is not a CloudFront alias |
| ACM validation name for `api.<domain>` | CNAME | The validation value ACM shows | M03A (O20) |
| `api` | CNAME | The `ApiCustomDomainTarget` output of the `findingalpha` stack | M03A, after the deploy that creates the domain |
| Three SES DKIM names | CNAME | The three SES values | M10 (O16) |
| `_dmarc` | TXT | A DMARC policy for the sending domain | M10 |

The `admin` record was added on 15 Nov 2026, DNS only. Its target is
the output named above. The hostname is not stored here, because a
replaced distribution would make a stored name wrong. Tick O08 on the
dashboard; this file does not change that tick.

The `api` record was added on 16 Nov 2026, DNS only. Its target is the
`ApiCustomDomainTarget` output. The hostname is not stored here. Tick
O20 on the dashboard; this file does not change that tick.

The public apex CNAME (DNS only) and the `www` → apex 301 redirect
(Worker custom domain, route, and Single Redirect) were added on
20 Nov 2026 after the owner said go. The CloudFront target and the
Worker script name are not stored here.

The ACM and SES values are not secret. The owner can paste them in
chat.

### O05 AWS access for GitHub Actions

Confirm these in the AWS account. None of them needs a value in git.

1. The SSM parameter `/cdk-bootstrap/siutindei/version` exists in
   `ap-southeast-1`. The deploy workflow checks it and stops with a
   clear error if it is missing.
2. The trust policy of `GitHubActionsRole` accepts this repository
   under its new name. Deploy jobs run in the `production` environment,
   so their token subject is
   `repo:lx-software-ltd/findingalpha:environment:production`. The
   pull-request diff uses
   `repo:lx-software-ltd/findingalpha:pull_request`. The `lx-software`
   setup guide says the role accepts every repository of the
   organisation, so this should already be true.
3. `GitHubActionsRole` may assume the `cdk-siutindei-*` roles.
4. `GitHubActionsRole` may, for the new stacks: describe the stacks
   `findingalpha` and `findingalpha-admin-web`, write to the web bucket,
   and create CloudFront invalidations. In `lx-software` these
   permissions may be limited to the `lxsoftware*` names. If so, the
   role's policy needs the `findingalpha*` names added. That is a
   change in the account, done by the owner.
5. For the key workflow (M03A): `GetItem`, `PutItem`, `UpdateItem` and
   `Query` on the table `findingalpha-records` and on its `gsi1` index,
   and `kms:Decrypt` and `kms:GenerateDataKey` on the shared key. The
   first **Manage Public API Keys** run fails with AccessDenied until
   these are on `GitHubActionsRole`.

The developer's own AWS user is read-only and narrow. It could not
read the bootstrap parameter, the role, the stacks or the
certificates, so none of the points above has been checked from the
developer's side.

### O10 Alpaca paper account

A paper-only account needs an email address and nothing else. The
secret value is JSON:

```json
{"key_id": "<paper key id>", "secret_key": "<paper secret>"}
```

Set it with the AWS console or `aws secretsmanager put-secret-value`.
The stack creates the secret empty. Never paste the value anywhere else.

### O12 and O13 Knowledge base

The bucket name is an output of the `findingalpha` stack
(`KbBucketName`). Supported file types: PDF, Markdown, text, HTML, Word,
Excel, CSV. Limit 50 MB a file. The total must stay under 2 GB or the
sync refuses to run and the dashboard says so.

`eval/questions.json` shape:

```json
[
  {
    "id": "q01",
    "question": "How is return on invested capital defined?",
    "expectedDocument": "file name of the PDF",
    "expectedText": "a short phrase that appears in the right passage",
    "page": 327,
    "formula": "the formula in plain text"
  }
]
```

`expectedDocument` is the file name without `theory/`. `expectedText`
is three to twelve plain words from one printed line beside the
formula: letters, digits and spaces only, so a hyphenated line break or
a ligature cannot hide it. `page` is the page a PDF viewer shows for
that file. `formula` is the expected answer, for the person who reads
the returned passages by hand. The evaluation scores a question on
`expectedDocument` and `expectedText` only.

### O14 OpenRouter key

The secret value is JSON: `{"findingalpha": "<key>"}`. Set a monthly
credit limit of 25 US dollars on the key itself in OpenRouter, so the
budget holds even if the code is wrong.

### O16 SES

If the account is in the SES sandbox, verifying the recipient address is
enough for one daily email to one person. Production access is not
needed.
