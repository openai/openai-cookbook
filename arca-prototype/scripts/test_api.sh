#!/usr/bin/env bash
# ARCA Prototype API — Reusable test script
# Usage: ./scripts/test_api.sh [cuit] [password]
# Or set ARCA_CUIT, ARCA_PASSWORD in .env (loaded from arca-prototype/.env)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Load .env if present
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

DO_FETCH=false
for arg in "$@"; do
  [ "$arg" = "--fetch" ] && DO_FETCH=true
done

CUIT="${1:-${ARCA_CUIT}}"
PASSWORD="${2:-${ARCA_PASSWORD}}"
BASE_URL="${ARCA_BASE_URL:-http://localhost:8000}"

# If first arg is --fetch, use env for creds
[ "$1" = "--fetch" ] && CUIT="${ARCA_CUIT}" && PASSWORD="${ARCA_PASSWORD}"

if [ -z "$CUIT" ] || [ -z "$PASSWORD" ]; then
  echo "Usage: $0 [cuit] [password] [--fetch]"
  echo "  --fetch: also run POST notificaciones-contenido (fetch from ARCA, ~30s)"
  echo "Or set ARCA_CUIT and ARCA_PASSWORD in .env"
  exit 1
fi

echo "=== ARCA API tests (base: $BASE_URL) ==="

# 1. Health
echo -e "\n--- Health ---"
curl -s "$BASE_URL/health" | head -1

# 2. GET from cache
echo -e "\n--- GET notifications (cache) ---"
curl -s "$BASE_URL/api/arca/notificaciones-contenido?cuit=$CUIT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('success:', d.get('success'), '| total:', d.get('total'), '| source:', d.get('source', 'N/A'))
"

# 3. POST fetch from ARCA (use --fetch to run, ~30s)
if [ "$DO_FETCH" = true ]; then
  echo -e "\n--- POST fetch from ARCA ---"
  curl -s -X POST "$BASE_URL/api/arca/notificaciones-contenido" \
    -H "Content-Type: application/json" \
    -d "{\"cuit\":\"$CUIT\",\"password\":\"$PASSWORD\"}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('success:', d.get('success'), '| total:', d.get('total'))
"
fi

# 4. GET PDF
echo -e "\n--- GET PDF (582958952) ---"
SIZE=$(curl -s -o /tmp/arca_test.pdf -w "%{size_download}" "$BASE_URL/api/arca/notificaciones/582958952/pdf?cuit=$CUIT")
if [ "$SIZE" -gt 50 ]; then
  echo "OK: PDF retrieved, $SIZE bytes"
else
  echo "404 or empty: PDF not in cache (upload first)"
fi

# 5. Upload PDF (if file exists)
UPLOAD_FILE="${PROJECT_DIR}/data/attachments/SCT-Intimacion.pdf"
if [ -f "$UPLOAD_FILE" ]; then
  echo -e "\n--- POST upload PDF ---"
  curl -s -X POST "$BASE_URL/api/arca/attachments/upload" \
    -F "cuit=$CUIT" \
    -F "notification_id=582958952" \
    -F "file=@$UPLOAD_FILE"
  echo
else
  echo -e "\n--- Upload skipped (no file at $UPLOAD_FILE) ---"
fi

echo -e "\n=== Done ==="
