#!/usr/bin/env bash
# Prepare a CDK diff or deploy. findingalpha keeps its parameter loader.
set -euo pipefail
mode="${1:-}"
case "$mode" in
  diff|deploy) ;;
  *) echo "::error::cdk-prepare.sh requires diff or deploy" >&2; exit 1 ;;
esac

write_csp_origin() {
  python3 - << 'PY'
import os
from pathlib import Path

region = os.environ.get("AWS_REGION", "")
if not region:
    raise SystemExit("AWS_REGION is required to build the Cognito prefix origin for CSP.")
prefix_origin = f"https://findingalpha-admin-auth.auth.{region}.amazoncognito.com"
domain = os.environ.get("P_COGNITO_DOMAIN", "")
cert = os.environ.get("P_COGNITO_CERT", "")
if domain and cert:
    origin = prefix_origin + " https://" + domain
else:
    origin = prefix_origin
for name in (
    "P_GOOGLE_CLIENT_SECRET",
    "P_EMAIL_ALLOWLIST",
    "P_BRIEF_RECIPIENT",
    "P_SEC_CONTACT",
    "P_CERT_ARN",
    "P_API_CERT",
    "P_COGNITO_CERT",
    "P_PUBLIC_CERT_ARN",
):
    value = os.environ.get(name, "")
    if value:
        print(f"::add-mask::{value}")
env_path = Path(os.environ["GITHUB_ENV"])
existing = env_path.read_text(encoding="utf-8")
if existing and not existing.endswith("\n"):
    existing += "\n"
env_path.write_text(existing + f"P_CSP_ORIGIN={origin}\n", encoding="utf-8")
PY
}

if [ ! -f backend/infrastructure/package.json ]; then
  echo "::warning::Missing backend/infrastructure/package.json"
  echo "run=false" >> "${GITHUB_OUTPUT:?}"
  exit 0
fi

if [ "$mode" = "deploy" ]; then
  mask_list() {
    local raw="$1"
    local part trimmed
    local -a parts
    if [ -z "$raw" ]; then
      return 0
    fi
    echo "::add-mask::${raw}"
    IFS=',' read -ra parts <<< "$raw"
    for part in "${parts[@]}"; do
      trimmed="${part#"${part%%[![:space:]]*}"}"
      trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
      if [ -n "$trimmed" ]; then
        echo "::add-mask::${trimmed}"
      fi
    done
  }
  warn_if_variable() {
    if [ "$1" = "true" ]; then
      echo "::warning::$2 is read from a variable, so this log shows it. Set the secret and delete the variable."
    fi
  }
  mask_list "${P_ACCOUNT_ID:-}"
  mask_list "${P_EMAIL_ALLOWLIST:-}"
  mask_list "${P_BRIEF_RECIPIENT:-}"
  mask_list "${P_SEC_CONTACT:-}"
  mask_list "${P_CERT_ARN:-}"
  mask_list "${P_PUBLIC_CERT_ARN:-}"
  mask_list "${P_COGNITO_CERT:-}"
  mask_list "${P_API_CERT:-}"
  warn_if_variable "${ALLOWLIST_FROM_VARIABLE:-}" "ADMIN_FEDERATED_EMAIL_ALLOWLIST"
  warn_if_variable "${BRIEF_FROM_VARIABLE:-}" "BRIEF_RECIPIENT_EMAIL"
  warn_if_variable "${SEC_FROM_VARIABLE:-}" "SEC_CONTACT_EMAIL"
  warn_if_variable "${ADMIN_CERT_FROM_VARIABLE:-}" "ADMIN_WEB_CERTIFICATE_ARN"
  warn_if_variable "${PUBLIC_CERT_FROM_VARIABLE:-}" "PUBLIC_WWW_CERTIFICATE_ARN"
  warn_if_variable "${COGNITO_CERT_FROM_VARIABLE:-}" "ADMIN_COGNITO_CUSTOM_DOMAIN_CERTIFICATE_ARN"
  warn_if_variable "${API_CERT_FROM_VARIABLE:-}" "API_CUSTOM_DOMAIN_CERTIFICATE_ARN"
  if [ -z "${P_ADMIN_DOMAIN:-}" ] || [ -z "${P_CERT_ARN:-}" ]; then
    echo "::error::Set ADMIN_WEB_DOMAIN_NAME and ADMIN_WEB_CERTIFICATE_ARN on the production environment before deploying."
    exit 1
  fi
  if [ -z "${P_PUBLIC_DOMAIN:-}" ] || [ -z "${P_PUBLIC_CERT_ARN:-}" ]; then
    echo "::notice::PUBLIC_WWW_DOMAIN_NAME or PUBLIC_WWW_CERTIFICATE_ARN is unset; findingalpha-public-www will be skipped."
  fi
  if [ -z "${P_ACCOUNT_ID:-}" ]; then
    echo "::error::Set AWS_ACCOUNT_ID as a repository secret before deploying."
    exit 1
  fi
  if [ -z "${P_EMAIL_ALLOWLIST:-}" ]; then
    echo "::error::Set ADMIN_FEDERATED_EMAIL_ALLOWLIST as a production secret or a variable before deploying."
    exit 1
  fi
  if { [ -n "${P_COGNITO_DOMAIN:-}" ] && [ -z "${P_COGNITO_CERT:-}" ]; } || \
     { [ -z "${P_COGNITO_DOMAIN:-}" ] && [ -n "${P_COGNITO_CERT:-}" ]; }; then
    echo "::error::Set both ADMIN_COGNITO_CUSTOM_DOMAIN_NAME and ADMIN_COGNITO_CUSTOM_DOMAIN_CERTIFICATE_ARN, or leave both empty."
    exit 1
  fi
  (
    cd backend/infrastructure
    npm run build --if-present
  )
  write_csp_origin
  {
    echo "run=true"
    echo "stacks=${CDK_STACKS:-}"
  } >> "${GITHUB_OUTPUT:?}"
  exit 0
fi

cd backend/infrastructure
npm run build --if-present
BACKEND_PARAM_ARGS=()
ADMIN_WEB_PARAM_ARGS=()
PUBLIC_WWW_PARAM_ARGS=()
resolve_param_file() {
  local path="$1"
  if [ -z "$path" ]; then
    return 1
  fi
  if [ -f "$path" ]; then
    echo "$path"
    return 0
  fi
  if [ -n "${GITHUB_WORKSPACE:-}" ] && [ -f "$GITHUB_WORKSPACE/$path" ]; then
    echo "$GITHUB_WORKSPACE/$path"
    return 0
  fi
  return 1
}
if [ -n "${CDK_PARAM_FILE:-}" ]; then
  RESOLVED_PARAM_FILE=$(resolve_param_file "$CDK_PARAM_FILE" || true)
  if [ -n "$RESOLVED_PARAM_FILE" ]; then
    # shellcheck source=../../scripts/deploy/cdk-params.sh
    source ../../scripts/deploy/cdk-params.sh
    cdk_load_param_args "$RESOLVED_PARAM_FILE"
  else
    echo "::error::CDK_PARAM_FILE was not found"
    exit 1
  fi
fi
PARAM_ARGS=( "${BACKEND_PARAM_ARGS[@]}" "${ADMIN_WEB_PARAM_ARGS[@]}" "${PUBLIC_WWW_PARAM_ARGS[@]}" )
if [ ${#PARAM_ARGS[@]} -gt 0 ]; then
  printf '%s\0' "${PARAM_ARGS[@]}" > "${RUNNER_TEMP:?}/cdk-args"
else
  : > "${RUNNER_TEMP:?}/cdk-args"
fi
STACK_ARGS=()
if [ -n "${CDK_STACKS:-}" ]; then
  IFS=$', \n\t' read -r -a STACK_LIST <<< "$CDK_STACKS"
  for stack in "${STACK_LIST[@]}"; do
    trimmed="${stack#"${stack%%[![:space:]]*}"}"
    trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
    if [ -n "$trimmed" ]; then
      STACK_ARGS+=("$trimmed")
    fi
  done
fi
if [ ${#STACK_ARGS[@]} -eq 0 ]; then
  STACK_ARGS=(findingalpha-public-www findingalpha findingalpha-admin-web)
fi
write_csp_origin
{
  echo "run=true"
  echo "stacks=${STACK_ARGS[*]}"
} >> "${GITHUB_OUTPUT:?}"
