#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap.
# Installs JS dependencies for every workspace that exists and the Python
# packages the Lambda unit tests import. Safe to re-run.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [ -f scripts/sync-brand-assets.sh ]; then
  echo "==> Syncing shared brand assets"
  bash scripts/sync-brand-assets.sh
fi

if [ -f apps/public_www/package.json ]; then
  echo "==> Installing public www dependencies (apps/public_www)"
  ( cd apps/public_www && npm ci )
fi

if [ -f apps/admin_web/package.json ]; then
  echo "==> Installing admin console dependencies (apps/admin_web)"
  ( cd apps/admin_web && npm ci )
fi

if [ -f backend/infrastructure/package.json ]; then
  echo "==> Installing CDK infrastructure dependencies (backend/infrastructure)"
  ( cd backend/infrastructure && npm ci )
fi

echo "==> Installing Python packages for Lambda unit tests"
# boto3/botocore ship in the Lambda Python 3.12 runtime but must be installed
# locally so the unittest suites work.
python3 -m pip install --user boto3 'ruff>=0.3.0'

# Provide non-secret placeholder VITE_* values so the admin dev server and
# `npm run build`/`npm test` resolve config. Real Cognito/API values belong in
# secrets, not the repo. Never overwrite an existing developer .env.
admin_env="apps/admin_web/.env"
if [ -f apps/admin_web/package.json ] && [ ! -f "$admin_env" ]; then
  echo "==> Writing placeholder $admin_env"
  cat > "$admin_env" <<'EOF'
VITE_COGNITO_CLIENT_ID=placeholder-client-id
VITE_COGNITO_DOMAIN=https://placeholder.auth.us-east-1.amazoncognito.com
VITE_COGNITO_REDIRECT_URI=http://localhost:5174/auth/callback
VITE_COGNITO_LOGOUT_URI=http://localhost:5174/
VITE_API_BASE_URL=https://placeholder.execute-api.us-east-1.amazonaws.com
EOF
fi

echo "==> Install complete"
