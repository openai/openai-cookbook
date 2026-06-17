#!/usr/bin/env bash
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/../../.." && pwd)"
VALIDATOR="${SCRIPT_DIR}/validate_assets.py"
REGISTRY_VALIDATOR="${SCRIPT_DIR}/validate_registry.py"
SOURCE_ONLY=0

usage() {
  cat <<'EOF'
Run validation for the Codex OpenTelemetry cookbook.

Usage
  validate.sh                 Local Docker, source, registry, unit, and shell checks.
  validate.sh --source-only   TOML, dashboard, registry, unit, and shell checks.

Tool overrides
  PYTHON_BIN                  Python 3.11+ interpreter
  DOCKER_BIN                  Docker executable with Compose

Validation requires the Python packages PyYAML and jsonschema. Notebook
validation also requires nbformat when the repository notebook checker is
available.
EOF
}

case "${1:-}" in
  "") ;;
  --source-only) SOURCE_ONLY=1 ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    printf 'ERROR - unknown argument - %s\n' "$1" >&2
    usage >&2
    exit 2
    ;;
esac

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  printf 'ERROR - Python executable not found - %s\n' "${PYTHON_BIN}" >&2
  exit 1
fi

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-otel-validation.XXXXXX")"
trap 'rm -rf "${TEMP_DIR}"' EXIT

pass() {
  printf 'PASS - %s\n' "$1"
}

skip() {
  printf 'SKIP - %s\n' "$1"
}

printf 'Running Codex OpenTelemetry cookbook validation\n'

shell_count=0
while IFS= read -r -d '' shell_file; do
  bash -n "${shell_file}"
  shell_count=$((shell_count + 1))
done < <(find "${SCRIPT_DIR}" "${ROOT_DIR}/tests" -type f -name '*.sh' -print0)
pass "shell syntax for ${shell_count} script(s)"

"${PYTHON_BIN}" -m unittest discover -s "${ROOT_DIR}/tests" -p 'test_*.py'
pass "Python validation tests"

"${PYTHON_BIN}" "${VALIDATOR}" --root "${ROOT_DIR}"
"${PYTHON_BIN}" "${REGISTRY_VALIDATOR}" \
  --registry "${REPO_ROOT}/registry.yaml" \
  --schema "${REPO_ROOT}/.github/registry_schema.json"

missing_requirements=0
DOCKER_BIN="${DOCKER_BIN:-docker}"
COMPOSE_FILE="${ROOT_DIR}/docker/docker-compose.yml"
if command -v "${DOCKER_BIN}" >/dev/null 2>&1 \
  && "${DOCKER_BIN}" compose version >/dev/null 2>&1; then
  "${DOCKER_BIN}" compose --file "${COMPOSE_FILE}" config --quiet
  pass "Docker Compose configuration"
elif [[ "${SOURCE_ONLY}" -eq 1 ]]; then
  skip "Docker Compose configuration because Docker Compose is not installed"
else
  printf 'ERROR - complete validation requires Docker Compose; install it or set DOCKER_BIN\n' >&2
  missing_requirements=1
fi

if [[ -f "${REPO_ROOT}/.github/scripts/check_notebooks.py" ]]; then
  if "${PYTHON_BIN}" -c 'import nbformat' >/dev/null 2>&1; then
    (
      cd "${REPO_ROOT}"
      "${PYTHON_BIN}" .github/scripts/check_notebooks.py
    )
    pass "repository notebook validation"
  elif [[ "${SOURCE_ONLY}" -eq 1 ]]; then
    skip "repository notebook validation because nbformat is not installed"
  else
    skip "repository notebook validation because nbformat is not installed"
  fi
fi

if [[ "${missing_requirements}" -ne 0 ]]; then
  exit 1
fi

printf 'Validation complete\n'
