#!/bin/sh
set -eu
: "${AGENTS_ENVIRONMENT_ID:?Set AGENTS_ENVIRONMENT_ID}"
: "${AGENTS_REMOTE_URL:?Set AGENTS_REMOTE_URL}"
: "${CODEX_API_KEY:?Set CODEX_API_KEY}"
umask 077
cd /workspace
# Keep registration diagnostics out of the gateway's captured process output.
exec /opt/codex/bin/codex exec-server \
  --remote "$AGENTS_REMOTE_URL" --environment-id "$AGENTS_ENVIRONMENT_ID" \
  >/dev/null 2>&1
