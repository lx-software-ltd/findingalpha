# Shared contracts

JSON files in this directory are the source of truth for values shared
across the admin SPA, the engine Lambda, and CDK.

After editing, run:

```bash
python3 scripts/sync-contracts.py
python3 scripts/check-contracts.py
```

Generated artifacts (see `docs/plans/reference.md` section 7):

- `backend/lambda/engine/contracts/` — copied JSON, except `roadmap.json`
- `backend/lambda/engine/contract_constants.py` — Python constants
- `apps/admin_web/src/lib/contracts/generated.ts` — TypeScript constants
- `backend/infrastructure/lib/shared-contracts.ts` — values the CDK app reads
