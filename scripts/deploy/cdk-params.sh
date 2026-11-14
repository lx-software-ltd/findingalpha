# Split a CDK parameter JSON file into --parameters argv arrays.
# Source from backend/infrastructure (deploy-backend.yml and cdk-diff.yml).
# cdk_load_param_args <resolved-param-file> sets:
#   BACKEND_PARAM_ARGS (keys starting findingalpha:)
#   ADMIN_WEB_PARAM_ARGS (keys starting findingalpha-admin-web:)
# A key with any other prefix, or with no prefix, is an error.
# Empty values are omitted.

cdk_load_param_args() {
  local resolved="$1"
  local backend_file admin_web_file unknown
  backend_file="$(mktemp)"
  admin_web_file="$(mktemp)"
  _cdk_params_cleanup() { rm -f "$backend_file" "$admin_web_file"; }
  unknown="$(jq -r 'keys[] | select(test("^(findingalpha:|findingalpha-admin-web:)") | not)' "$resolved")"
  if [[ -n "$unknown" ]]; then
    echo "unknown parameter key prefix:" >&2
    echo "$unknown" >&2
    _cdk_params_cleanup
    return 1
  fi
  if ! jq -r 'to_entries[] | select(.value != null) | .value = (if .value | type == "string" then .value else (.value | tostring) end) | .value = (.value | gsub("\r\n"; "\n") | gsub("\r"; "\n") | gsub("\n"; "\\n") | ltrimstr(" ") | rtrimstr(" ")) | select(.value != "") | select(.key | startswith("findingalpha:")) | "--parameters", "\(.key)=\(.value)"' "$resolved" > "$backend_file"; then
    _cdk_params_cleanup
    return 1
  fi
  if ! jq -r 'to_entries[] | select(.value != null) | .value = (if .value | type == "string" then .value else (.value | tostring) end) | .value = (.value | gsub("\r\n"; "\n") | gsub("\r"; "\n") | gsub("\n"; "\\n") | ltrimstr(" ") | rtrimstr(" ")) | select(.value != "") | select(.key | startswith("findingalpha-admin-web:")) | "--parameters", "\(.key)=\(.value)"' "$resolved" > "$admin_web_file"; then
    _cdk_params_cleanup
    return 1
  fi
  BACKEND_PARAM_ARGS=()
  ADMIN_WEB_PARAM_ARGS=()
  readarray -t BACKEND_PARAM_ARGS < "$backend_file"
  readarray -t ADMIN_WEB_PARAM_ARGS < "$admin_web_file"
  _cdk_params_cleanup
}
