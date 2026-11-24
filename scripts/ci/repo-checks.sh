#!/usr/bin/env bash
set -euo pipefail
bash scripts/sync-brand-assets.sh --check
python3 scripts/check-contracts.py
