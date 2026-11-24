# Finding Alpha public website

Single page: dark background, brand logo centred, nothing else.

Shared favicons and `icon.png` live in `brand/` at the repo root.
`scripts/sync-brand-assets.sh` copies them into `public/` (also run from
`prebuild`).

## Local

```bash
npm install
npm run dev
```

Dev server: `http://localhost:5173/` (port from `vite.config.ts`).

## Checks

```bash
npm test
npm run lint
npm run build
npm run preview
```

## Lighthouse

`.lighthouserc.json` is the base config for **Lighthouse Public Website**.
The shared `lighthouse-ci` action rewrites the collect URL from the
workflow input (empty means `/`) and runs `@lhci/cli` against `dist/`.
The distribution does not rewrite unknown paths to `index.html`, so the
config leaves `isSinglePageApplication` off.

Locally, after `npm run build`:

```bash
npx --yes @lhci/cli@0.15.1 autorun
```

## Deploy

Hosting is the `findingalpha-public-www` stack (S3 + CloudFront).
**Deploy Backend** creates or updates it when `PUBLIC_WWW_DOMAIN_NAME`
and `PUBLIC_WWW_CERTIFICATE_ARN` are set; otherwise that stack is
skipped. **Deploy Public Website** uploads `dist/` after a successful
backend deploy (or on push to `apps/public_www/**` on `main`), and
skips when the stack is not present yet.

See `docs/deployment/public-website.md`.
