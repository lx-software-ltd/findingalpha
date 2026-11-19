# Brand assets

Canonical copies of shared favicons and the admin/public icon.

| File | Used by |
| --- | --- |
| `favicon.ico`, `favicon.svg`, `favicon-32.png`, `apple-touch-icon.png` | `apps/public_www`, `apps/admin_web` |
| `icon.png` | Admin login; also copied to public www |

Run `scripts/sync-brand-assets.sh` after editing here (also hooked as
`prebuild` in both apps). `scripts/sync-brand-assets.sh --check` fails
when the Vite `public/` copies drift.

`apps/public_www/public/logo.png` stays app-local (hero logo).
