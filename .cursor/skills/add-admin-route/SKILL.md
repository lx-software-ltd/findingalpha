---
name: add-admin-route
description: Add an admin HTTP route across the Lambda, the CDK integration, the SPA client, and the mock API.
---

# Add an admin route

1. Handle the route in `backend/lambda/engine/api_handler.py` and call `_require_admin` (`http_common.py`). Adding that route is yellow. Changing `_require_admin` is red (`docs/architecture/zones.md`).
2. Register the path with `SharedPermissionLambdaIntegration`. Do not add a per-route Lambda permission.
3. Set the route's key scope, or mark it owner only, in the route table and in `docs/plans/reference.md` section 8.
4. Call it from `apps/admin_web` through the admin API client.
5. Add the fixture response so `npm run dev:mock` serves it.
6. Cover the handler in the matching `test_*.py`.
