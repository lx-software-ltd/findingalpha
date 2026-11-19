#!/usr/bin/env bash
# Copy shared brand assets from brand/ into the Vite public dirs.
# Usage:
#   scripts/sync-brand-assets.sh          # copy
#   scripts/sync-brand-assets.sh --check  # fail if copies drift
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/brand"
TARGETS=(
  "$ROOT/apps/public_www/public"
  "$ROOT/apps/admin_web/public"
)
FILES=(
  favicon.ico
  favicon.svg
  favicon-32.png
  apple-touch-icon.png
  icon.png
)

check=false
if [ "${1:-}" = "--check" ]; then
  check=true
fi

for file in "${FILES[@]}"; do
  if [ ! -f "$SRC/$file" ]; then
    echo "missing brand source: $SRC/$file" >&2
    exit 1
  fi
done

for dest in "${TARGETS[@]}"; do
  mkdir -p "$dest"
  for file in "${FILES[@]}"; do
    if $check; then
      if [ ! -f "$dest/$file" ] || ! cmp -s "$SRC/$file" "$dest/$file"; then
        echo "brand asset out of sync: $dest/$file (run scripts/sync-brand-assets.sh)" >&2
        exit 1
      fi
    else
      cp "$SRC/$file" "$dest/$file"
    fi
  done
done

if $check; then
  echo "brand assets match brand/"
else
  echo "synced brand assets into public_www and admin_web"
fi
