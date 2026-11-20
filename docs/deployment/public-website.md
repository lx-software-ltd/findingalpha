# Public website

Runbook for the `findingalpha-public-www` stack and the logo-only site
in `apps/public_www`.

## Stack

- Origin bucket `findingalpha-public-www-<account>-<region>` (private,
  TLS-only, versioned, RETAIN)
- Access logs bucket `findingalpha-public-www-logs-<account>-<region>`
  (90-day expiry for current and noncurrent versions)
- CloudFront distribution with HTTPS redirect and a tight
  Content-Security-Policy (no analytics hosts). Unknown paths keep
  real 403/404 responses (no SPA rewrite to `index.html`).

Parameters (GitHub `production` environment, not git):

| Parameter | Variable |
| --- | --- |
| `PublicWebsiteDomainName` | `PUBLIC_WWW_DOMAIN_NAME` |
| `PublicWebsiteCertificateArn` | `PUBLIC_WWW_CERTIFICATE_ARN` (ACM in us-east-1) |
| `WafWebAclArn` | `PUBLIC_WWW_WAF_WEB_ACL_ARN` (optional) |

**Deploy Backend** deploys `findingalpha` and `findingalpha-admin-web`
first, then `findingalpha-public-www` only when both public domain and
certificate variables are set. Empty public vars skip that stack so
backend deploys are not blocked.

**Deploy Public Website** builds `apps/public_www` and runs
`scripts/deploy/deploy-public-website.sh`. It also runs after a
successful **Deploy Backend** on `main`, and skips when the app or the
CloudFormation stack is missing.

## Local

```bash
cd apps/public_www
npm ci
npm run build
npm run preview
```

## First publish checklist

1. Request an ACM certificate in `us-east-1` for the public hostname.
2. Set `PUBLIC_WWW_DOMAIN_NAME` and `PUBLIC_WWW_CERTIFICATE_ARN`.
3. Merge or re-run **Deploy Backend** so it creates
   `findingalpha-public-www` (after the backend and admin stacks).
4. Create the Cloudflare DNS records after the owner says go (see
   below).
5. **Deploy Public Website** uploads `dist/` automatically after a
   successful backend deploy, or on push to `apps/public_www/**` on
   `main`.

## DNS (Cloudflare)

The stack parameter is the canonical public hostname. When that value
is the apex (`PUBLIC_WWW_DOMAIN_NAME=<domain>`):

1. **Apex** — CNAME to `PublicWebsiteDistributionDomain`, DNS only
   (grey cloud). Cloudflare flattens the apex. Do not proxy the apex;
   CloudFront terminates TLS with the ACM certificate.
2. **`www`** — not a CloudFront alias. Attach a Worker custom domain on
   `www.<domain>` (proxied `AAAA 100::`), a Worker route
   `www.<domain>/*`, and a Single Redirect that 301s to
   `https://<domain>` while keeping the path and query. The Worker is
   the fallback when the Single Redirect is absent.

When the canonical hostname is `www.<domain>` instead, invert the
pattern (www CNAME DNS-only to CloudFront; apex redirects to www), as
on the sibling public site.

Do not write the live domain or the CloudFront hostname in git.
