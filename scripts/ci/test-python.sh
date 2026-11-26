#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install boto3
for dir in backend/lambda/engine backend/lambda/pre_token_generation backend/lambda/public_api_authorizer; do
  if [ -d "$dir" ]; then
    python3 -m unittest discover -s "$dir" -p 'test_*.py' -v
  fi
done
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/check_openapi_routes.py
