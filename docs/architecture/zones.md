# Agent work zones

Autonomy follows blast radius. A person draws this map. A change that
touches more than one zone uses the stricter zone. If implementation
spreads into a stricter zone, stop and ask.

## Red

Plan in chat and wait for explicit approval before any write. A human
pairs on the change. The listed engine files can move money or
change limits.

- `backend/infrastructure/**`
- `backend/lambda/pre_token_generation/**`
- `_require_admin` in `backend/lambda/engine/http_common.py`
- `backend/lambda/engine/broker.py`, `broker_alpaca.py`, `orders.py`,
  `leverage.py`, `limits.py`, `kill_switch.py`, `breakers.py`,
  `holds.py`
- `contracts/**` except `contracts/roadmap.json`
- `scripts/deploy/**`
- `scripts/pii-denylist.sha256`
- `.github/workflows/deploy-*.yml`
- `.cursor/hooks.json`, `.cursor/hooks/**`
- `.pre-commit-config.yaml`

## Yellow

Write a short plan from `docs/plans/_template.md` before editing. Add
or update tests first, then implement.

- Remaining `backend/lambda/**`
- `apps/admin_web/src/**`
- `apps/public_www/**` (logo-only public site; pushes to `main` deploy)

## Green

Implement and verify. Summarise intent in the pull request.

- `docs/**`
- `contracts/roadmap.json`
- `.cursor/mcp.json` (local MCP config; it does not deploy)
- Test-only edits that do not sit on a red path

Hooks still format edits and block destructive commands in every zone.
CI remains the merge gate.
