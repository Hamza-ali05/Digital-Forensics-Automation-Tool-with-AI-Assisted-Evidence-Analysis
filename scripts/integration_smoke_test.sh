#!/usr/bin/env bash
# Smoke test: verify backend-frontend integration
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE="${DFAT_API_BASE:-http://localhost:8000/api/v1}"
# Credentials match scripts/seed_dev_data.py (override via env if needed).
SMOKE_USER="${DFAT_SMOKE_USER:-admin}"
SMOKE_PASS="${DFAT_SMOKE_PASSWORD:-Admin!Pass#2026}"

echo "=== DFAT Integration Smoke Test ==="
echo "API: ${API_BASE}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $1" >&2
    exit 1
  fi
}

require_cmd curl
require_cmd jq

# 1. Health check
echo "1. Health check..."
curl -sf "${API_BASE}/health" | jq -r .status

# 2. Login
echo "2. Login..."
TOKEN=$(
  curl -sf -X POST "${API_BASE}/auth/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=${SMOKE_USER}&password=${SMOKE_PASS}" | jq -r .access_token
)
if [[ -z "${TOKEN}" || "${TOKEN}" == "null" ]]; then
  echo "ERROR: login did not return an access_token (run: make seed-dev)" >&2
  exit 1
fi

# 3. Get profile
echo "3. Get profile..."
curl -sf "${API_BASE}/users/me" \
  -H "Authorization: Bearer ${TOKEN}" | jq -r .username

# 4. Create case
echo "4. Create case..."
CASE_ID=$(
  curl -sf -X POST "${API_BASE}/cases" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"case_name":"Smoke Test Case","description":"Integration test"}' \
    | jq -r .case_id
)
echo "   case_id=${CASE_ID}"

# 5. List cases
echo "5. List cases..."
curl -sf "${API_BASE}/cases" \
  -H "Authorization: Bearer ${TOKEN}" | jq .total

# 6. AI health
echo "6. AI health..."
curl -sf "${API_BASE}/ai/health" | jq .is_healthy

# 7. Frontend build check
echo "7. Frontend build..."
(
  cd "${ROOT_DIR}/frontend"
  export NODE_OPTIONS="${NODE_OPTIONS:---openssl-legacy-provider}"
  export CI=true
  npm run build
)

echo "=== All smoke tests passed ==="
