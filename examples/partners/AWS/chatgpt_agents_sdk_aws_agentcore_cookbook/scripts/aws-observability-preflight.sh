#!/usr/bin/env bash

# Read-only diagnostics for the local ADOT publisher or an existing Runtime verifier.
# This script never enables Transaction Search, creates a log group, changes a policy,
# assumes a role, or invokes a model/runtime.

set -u

log_group="${COOKBOOK_TRACE_VERIFICATION_LOG_GROUP:-${LOCAL_AGENT_LOG_GROUP:-aws/spans}}"
mode="${COOKBOOK_EXECUTION_MODE:-}"
case "$mode" in
  ""|local|deployed) ;;
  *) echo "CHECK NEEDED: COOKBOOK_EXECUTION_MODE must be local or deployed." >&2; exit 1 ;;
esac
case "${FLIGHT_DATA_SOURCE:-}" in
  "") legacy_mode="" ;;
  local-agent) legacy_mode="local" ;;
  agentcore-runtime) legacy_mode="deployed" ;;
  *) echo "CHECK NEEDED: FLIGHT_DATA_SOURCE must be local-agent or agentcore-runtime." >&2; exit 1 ;;
esac
if [[ -n "$mode" && -n "$legacy_mode" && "$mode" != "$legacy_mode" ]]; then
  echo "CHECK NEEDED: COOKBOOK_EXECUTION_MODE conflicts with legacy FLIGHT_DATA_SOURCE." >&2
  exit 1
fi
mode="${mode:-${legacy_mode:-local}}"

if [[ "$mode" == "local" && -n "${AWS_REGION:-}" && -n "${AWS_DEFAULT_REGION:-}" && "$AWS_REGION" != "$AWS_DEFAULT_REGION" ]]; then
  cat >&2 <<'EOF'
CHECK NEEDED: AWS_REGION and AWS_DEFAULT_REGION must match. Set AWS_REGION in
the repository-root .env and remove or correct the conflicting shell value.
EOF
  exit 1
fi
region="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
if [[ "$mode" == "deployed" ]]; then
  region="${AGENTCORE_RUNTIME_REGION:-$region}"
fi

failures=0

check() {
  local label="$1"
  shift
  if "$@"; then
    printf '\nPASS: %s\n' "$label"
  else
    local status=$?
    printf '\nCHECK NEEDED: %s (command exited %s)\n' "$label" "$status" >&2
    failures=1
  fi
}

if ! command -v aws >/dev/null 2>&1; then
  echo "CHECK NEEDED: AWS CLI is not installed or not on PATH." >&2
  exit 1
fi

if [[ -z "$region" ]]; then
  region="$(aws configure get region 2>/dev/null || true)"
fi

if [[ -z "$region" ]]; then
  cat >&2 <<'EOF'
CHECK NEEDED: AWS Region is missing. Set AWS_REGION (or AGENTCORE_RUNTIME_REGION
for deployed mode) in the repository-root .env, or configure the selected AWS
profile. Then run the documented preflight command from the repository root.
EOF
  exit 1
fi

echo "Read-only AWS observability preflight"
echo "Execution mode: $mode"
echo "Region: $region"
echo "Trace log group: $log_group"

check "caller identity and selected account" \
  aws --no-cli-pager sts get-caller-identity --region "$region" --output table

check "CloudWatch Transaction Search destination state" \
  aws --no-cli-pager xray get-trace-segment-destination --region "$region" --output table

check "CloudWatch Logs resource-policy visibility for X-Ray span delivery" \
  aws --no-cli-pager logs describe-resource-policies \
    --region "$region" \
    --query 'resourcePolicies[].policyName' \
    --output table

check "configured span log-group visibility and retention" \
  aws --no-cli-pager logs describe-log-groups \
    --region "$region" \
    --log-group-name-prefix "$log_group" \
    --query 'logGroups[].{name:logGroupName,retentionDays:retentionInDays}' \
    --output table

check "recent stream visibility in the configured span log group" \
  aws --no-cli-pager logs describe-log-streams \
    --region "$region" \
    --log-group-name "$log_group" \
    --order-by LastEventTime \
    --descending \
    --max-items 5 \
    --query 'logStreams[].{name:logStreamName,lastEvent:lastEventTimestamp}' \
    --output table

# The AWS CLI query uses literal backticks; shell expansion must remain disabled.
# shellcheck disable=SC2016
check "CloudWatch Logs quota catalog visibility" \
  aws --no-cli-pager service-quotas list-service-quotas \
    --region "$region" \
    --service-code logs \
    --max-items 100 \
    --query 'Quotas[?contains(QuotaName, `PutLogEvents`) || contains(QuotaName, `CreateLogStream`)].{name:QuotaName,value:Value,adjustable:Adjustable}' \
    --output table

if [[ "$failures" -ne 0 ]]; then
  cat >&2 <<'EOF'

The failed checks are read-only evidence of a missing identity, Region, permission,
or prerequisite. A developer must not create account resources to clear them. Route
Transaction Search, X-Ray destination, CloudWatch resource-policy, quota, SCP, and
permission-boundary work to the AWS account or organization administrator.
EOF
  exit 1
fi

cat <<'EOF'

Read-only diagnostics completed. This does not verify that a trace was ingested.
Run trace_smoke.py, then verify_traces.py with its correlation ID. OpenAI Traces,
when COOKBOOK_TRACING_MODE=dual, still requires named manual confirmation.
EOF
