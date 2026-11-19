# Public website

Runbook for the `findingalpha-public-www` stack and the logo-only site
in `apps/public_www`.

## Stack

- Origin bucket `findingalpha-public-www-<account>-<region>` (private,
  TLS-only, versioned, RETAIN)
- Access logs bucket `findingalpha-public-www-logs-<account>-<region>`
- CloudFront distribution with HTTPS redirect, SPA rewrite, and a tight
  Content-Security-Policy (no analytics hosts)

Parameters (GitHub `production` environment, not git):

| Parameter | Variable |
| --- | --- |
| `PublicWebsiteDomainName` | `PUBLIC_WWW_DOMAIN_NAME` |
| `PublicWebsiteCertificateArn` | `PUBLIC_WWW_CERTIFICATE_ARN` (ACM in us-east-1) |
| `WafWebAclArn` | `PUBLIC_WWW_WAF_WEB_ACL_ARN` (optional) |

**Deploy Backend** creates or updates the stack. **Deploy Public
Website** builds `apps/public_www` and runs
`scripts/deploy/deploy-public-website.sh`.

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
3. Merge so **Deploy Backend** creates `findingalpha-public-www`.
4. Create the Cloudflare DNS CNAME (DNS only) after the owner says go.
5. Push or run **Deploy Public Website** to upload `dist/`.
