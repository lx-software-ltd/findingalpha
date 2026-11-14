# Split a CDK parameter JSON file into --parameters argv arrays.
# Source from backend/infrastructure. Sets BACKEND_PARAM_ARGS and ADMIN_WEB_PARAM_ARGS.
# Keys must be findingalpha:<Name> or findingalpha-admin-web:<Name>.

cdk_load_param_args() {
  local resolved="$1"
  local backend_file admin_web_file unknown
  backend_file="$(mktemp)"
  admin_web_file="$(mktemp)"
  _cdk_params_cleanup() { rm -f "$backend_file" "$admin_web_file"; }
  unknown="$(jq -r 'to_entries[] | select(.value != null) | .key | select(test("^(findingalpha:|findingalpha-admin-web:)") | not)' "$resolved")"
  if [[ -n "$unknown" ]]; then
    echo "unknown parameter key prefix:" >&2
    echo "$unknown" >&2
    _cdk_params_cleanup
    return 1
  fi
  if ! jq -r 'to_entries[] | select(.value != null) | .value = (if .value | type == "string" then .value else (.value | tostring) end) | select(.value != "") | select(.key | test("^findingalpha:")) | "--parameters", "\(.key)=\(.value)"' "$resolved" > "$backend_file"; then
    _cdk_params_cleanup
    return 1
  fi
  if ! jq -r 'to_entries[] | select(.value != null) | .value = (if .value | type == "string" then .value else (.value | tostring) end) | select(.value != "") | select(.key | test("^findingalpha-admin-web:")) | "--parameters", "\(.key)=\(.value)"' "$resolved" > "$admin_web_file"; then
    _cdk_params_cleanup
    return 1
  fi
  BACKEND_PARAM_ARGS=()
  ADMIN_WEB_PARAM_ARGS=()
  readarray -t BACKEND_PARAM_ARGS < "$backend_file"
  readarray -t ADMIN_WEB_PARAM_ARGS < "$admin_web_file"
  _cdk_params_cleanup
}
