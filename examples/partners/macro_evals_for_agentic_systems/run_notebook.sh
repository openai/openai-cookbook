#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
NOTEBOOK_PATH="${NOTEBOOK_PATH:-macro_evals_for_agentic_systems.ipynb}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs}"
TRACE_LIMIT="${MACRO_EVALS_TRACE_LIMIT:-}"

"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit(
        "Python 3.11 or newer is required. "
        "Set PYTHON_BIN=/path/to/python3.11 and rerun this script."
    )
PY

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --only-binary=:all: -r requirements.txt

export JUPYTER_CONFIG_DIR="${JUPYTER_CONFIG_DIR:-$PWD/.jupyter}"
export IPYTHONDIR="${IPYTHONDIR:-$PWD/.ipython}"
mkdir -p "$JUPYTER_CONFIG_DIR" "$IPYTHONDIR"
mkdir -p "$OUTPUT_DIR"

if [[ -n "$TRACE_LIMIT" ]]; then
  echo "Running notebook with MACRO_EVALS_TRACE_LIMIT=$TRACE_LIMIT"
fi

python -m jupyter nbconvert \
  --to notebook \
  --execute "$NOTEBOOK_PATH" \
  --output-dir "$OUTPUT_DIR" \
  --output executed_notebook.ipynb

python -m jupyter nbconvert \
  --to html \
  "$OUTPUT_DIR/executed_notebook.ipynb" \
  --output macro_evals_cookbook.html

echo "Wrote $OUTPUT_DIR/executed_notebook.ipynb"
echo "Wrote $OUTPUT_DIR/macro_evals_cookbook.html"
