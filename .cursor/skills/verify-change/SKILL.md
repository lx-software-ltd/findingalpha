---
name: verify-change
description: Choose the commands that prove a change and record the evidence in the pull request.
---

# Verify a change

Run the narrowest command that exercises the edit, then the area lint. Paste the commands and the result into the pull request.

- Admin web unit: `npm run test:unit` in `apps/admin_web`. `npm test` is the right command when a page changed.
- Admin web browser: `npm run dev:mock`, then exercise the changed flow. `npm run test:e2e` when layout or navigation changed.
- Engine: `python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py' -v`
- One other Lambda: `python3 -m unittest discover -p 'test_*.py' -v` in that Lambda directory. The same command covers `backend/lambda/pre_token_generation` and `backend/lambda/public_api_authorizer`.
- CDK: `npm test` and `npm run build` in `backend/infrastructure` when a stack changed.
- Contracts: `python3 scripts/sync-contracts.py` then `python3 scripts/check-contracts.py`.
- Personal data: `python3 scripts/check_pii.py`.
- Agent rules: `python3 scripts/validate_agent_rules.py`.
- Python style: `python3 -m ruff check backend/lambda scripts .cursor/hooks`.

A UI behavior change is verified in the browser (click, type, submit, and the other screens that share the state).

## Done

The pull request lists the zone, the checks you ran, and whether docs or contracts changed. CI remains the merge gate. Cloud agents do not fire the `stop` hook.
