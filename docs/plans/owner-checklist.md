# Owner checklist

Things only the owner can do. A developer or agent must not attempt
them and must not ask for secret values in chat. Each item says what it
blocks. The dashboard shows this list with tick boxes from M03.

Values that identify a person or an account go into the GitHub
`production` environment or AWS Secrets Manager. They never go into
git, a pull request, or chat.

| Id | Task | Blocks |
| --- | --- | --- |
| O01 | Choose and register the new domain. Add it to Cloudflare DNS | First deploy (M02), email (M10) |
| O02 | Protect `main`: pull request required, required checks `lint` and `test`, no force-push | Merging M01 safely |
| O03 | Produce the PII denylist hashes (step in M01) and hand over the hash file | M01 |
| O04 | Create the GitHub environment `production` in `findingalpha` with the variables and secrets in `reference.md` section 3 | First deploy (M02) |
| O05 | Confirm AWS access for GitHub Actions (details below) | First deploy (M02) |
| O06 | Request an ACM certificate for `admin.<domain>` in `us-east-1`, validate by DNS with Cloudflare proxy off, wait for ISSUED | First deploy (M02) |
| O07 | Create a Google OAuth client (type Web application). Authorised redirect URI: `https://<cognito-domain>/oauth2/idpresponse` | First sign-in (M02) |
| O08 | After the first deploy: CNAME `admin.<domain>` to the CloudFront domain, proxy off | Dashboard reachable (M03) |
| O09 | Sign in once with the bootstrap user, set a new password, enrol TOTP | Dashboard use (M03) |
| O10 | Open a free Alpaca paper account. Set the paper balance to the planned capital in US dollars. Store the paper API key in the secret `findingalpha/alpaca-paper` | M04 |
| O11 | Review the provisional formulas listed in M05 and say which to keep | M05 merge |
| O12 | Upload the PDFs to the knowledge base bucket under `theory/`. Split any file over 50 MB | M07 |
| O13 | Write 20 questions whose answers are formulas in the PDFs, with the book and page. Upload as `eval/questions.json` | M07 evaluation |
| O14 | Add `findingalpha` to `contracts/openrouter-apps.json` in `lx-software` (red zone there), mint the key, store it in the secret `findingalpha/openrouter` | M08 |
| O15 | Confirm the tax figures in M09 with an adviser (dividend withholding rate, estate-tax schedule) | M09 register status |
| O16 | Verify the sending domain in SES (three DKIM CNAMEs in Cloudflare) and verify the recipient address | M10 |
| O17 | Run the kill-switch and breaker drill with the developer | M11 |
| O18 | Decide on real money after the gate report is green | M12 |

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

### O05 AWS access for GitHub Actions

Confirm these in the AWS account. None of them needs a value in git.

1. The SSM parameter `/cdk-bootstrap/siutindei/version` exists in
   `ap-southeast-1`. The deploy workflow checks it and stops with a
   clear error if it is missing.
2. The trust policy of `GitHubActionsRole` accepts this repository. The
   `lx-software` setup guide says it accepts every repository of the
   organisation, so this should already be true.
3. `GitHubActionsRole` may assume the `cdk-siutindei-*` roles.
4. `GitHubActionsRole` may, for the new stacks: describe the stacks
   `findingalpha` and `findingalpha-admin-web`, write to the web bucket,
   and create CloudFront invalidations. In `lx-software` these
   permissions may be limited to the `lxsoftware*` names. If so, the
   role's policy needs the `findingalpha*` names added. That is a
   change in the account, done by the owner.

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
    "expectedText": "a short phrase that appears in the right passage"
  }
]
```

### O14 OpenRouter key

The secret value is JSON: `{"findingalpha": "<key>"}`. Set a monthly
credit limit of 25 US dollars on the key itself in OpenRouter, so the
budget holds even if the code is wrong.

### O16 SES

If the account is in the SES sandbox, verifying the recipient address is
enough for one daily email to one person. Production access is not
needed.
