#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
APP_DIR="$ROOT_DIR/apps/public_www"
BUILD_DIR="$APP_DIR/dist"
STACK_NAME="${PUBLIC_WEBSITE_STACK_NAME:-findingalpha-public-www}"
IMMUTABLE="public,max-age=31536000,immutable"

if [ ! -d "$BUILD_DIR" ]; then
  echo "Build output not found at $BUILD_DIR"
  echo "Run: (cd apps/public_www && npm run build)"
  exit 1
fi

BUCKET_QUERY="Stacks[0].Outputs[?OutputKey=='PublicWebsiteBucketName']."
BUCKET_QUERY+="OutputValue"
BUCKET_NAME="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "$BUCKET_QUERY" \
  --output text)"

if [ -z "$BUCKET_NAME" ] || [ "$BUCKET_NAME" = "None" ]; then
  echo "Public website bucket output not found for $STACK_NAME"
  exit 1
fi

content_type() {
  case "$1" in
    *.html) printf '%s' "text/html; charset=utf-8" ;;
    *.json) printf '%s' "application/json; charset=utf-8" ;;
    *.txt) printf '%s' "text/plain; charset=utf-8" ;;
    *.xml) printf '%s' "application/xml; charset=utf-8" ;;
    *.svg) printf '%s' "image/svg+xml" ;;
    *.png) printf '%s' "image/png" ;;
    *.jpg|*.jpeg) printf '%s' "image/jpeg" ;;
    *.webp) printf '%s' "image/webp" ;;
    *.ico) printf '%s' "image/x-icon" ;;
    *.js) printf '%s' "text/javascript; charset=utf-8" ;;
    *.css) printf '%s' "text/css; charset=utf-8" ;;
    *) printf '%s' "application/octet-stream" ;;
  esac
}

upload_file() {
  local path="$1"
  local key="$2"
  local cache
  case "$key" in
    assets/*) cache="$IMMUTABLE" ;;
    *) cache="no-cache,must-revalidate" ;;
  esac
  aws s3 cp "$path" "s3://$BUCKET_NAME/$key" \
    --cache-control "$cache" \
    --content-type "$(content_type "$path")"
}

if [ -d "$BUILD_DIR/assets" ]; then
  echo "Uploading hashed assets under dist/assets with long cache…"
  aws s3 sync "$BUILD_DIR/assets" "s3://$BUCKET_NAME/assets" \
    --delete \
    --cache-control "$IMMUTABLE"
fi

echo "Uploading site root files…"
shopt -s nullglob
for path in "$BUILD_DIR"/*; do
  [ -f "$path" ] || continue
  base="$(basename "$path")"
  [ "$base" = "index.html" ] && continue
  upload_file "$path" "$base"
done

echo "Uploading index.html last with no-cache…"
aws s3 cp "$BUILD_DIR/index.html" "s3://$BUCKET_NAME/index.html" \
  --cache-control "no-cache,must-revalidate" \
  --content-type "text/html; charset=utf-8"

DISTRIBUTION_QUERY="Stacks[0].Outputs[?OutputKey=='PublicWebsiteDistributionId']."
DISTRIBUTION_QUERY+="OutputValue"
DISTRIBUTION_ID="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "$DISTRIBUTION_QUERY" \
  --output text)"

if [ -n "$DISTRIBUTION_ID" ] && [ "$DISTRIBUTION_ID" != "None" ]; then
  echo "Invalidating CloudFront distribution $DISTRIBUTION_ID"
  aws cloudfront create-invalidation \
    --distribution-id "$DISTRIBUTION_ID" \
    --paths "/*"
fi
