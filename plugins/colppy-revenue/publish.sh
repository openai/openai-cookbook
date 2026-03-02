#!/bin/bash
# Build colppy-revenue plugin zip for Claude Cowork upload.
# Output: ../../tools/outputs/colppy-revenue-plugin-full.zip

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGINS_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$REPO_ROOT/tools/outputs"
ZIP_NAME="colppy-revenue-plugin-full.zip"

mkdir -p "$OUTPUT_DIR"

echo "Building plugin zip..."
cd "$PLUGINS_DIR"
zip -r "$OUTPUT_DIR/$ZIP_NAME" colppy-revenue \
  -x "*.git*" \
  -x "colppy-revenue/publish.sh" \
  -x "*.DS_Store" \
  -x "colppy-revenue/tools/*"
echo "Created: $OUTPUT_DIR/$ZIP_NAME"
