#!/usr/bin/env bash
# DFAT one-click launcher for macOS / Linux.
# Make executable: chmod +x start.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}/src"
export DFAT_ENV=development
export PYTHONDONTWRITEBYTECODE=1
export BROWSER=none

BACKEND_PID_FILE="${ROOT}/.dfat_backend.pid"
FRONTEND_PID_FILE="${ROOT}/.dfat_frontend.pid"
DB_FILE="${ROOT}/data/dfat.db"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

BACKEND_PID=""
FRONTEND_PID=""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
timestamp() {
  date +"%H:%M:%S"
}

log() {
  echo -e "${CYAN}[$(timestamp)]${NC} $*"
}

log_ok() {
  echo -e "${GREEN}[$(timestamp)]${NC} $*"
}

log_warn() {
  echo -e "${YELLOW}[$(timestamp)]${NC} $*"
}

log_err() {
  echo -e "${RED}[$(timestamp)]${NC} $*" >&2
}

version_compare() {
  # usage: version_compare "18.17.0" "18"  -> 0 if first >= second major.minor
  local ver="${1#v}"
  local min="${2#v}"
  local ver_major min_major
  ver_major="$(echo "$ver" | cut -d. -f1)"
  min_major="$(echo "$min" | cut -d. -f1)"
  if [[ "$ver_major" -lt "$min_major" ]]; then
    return 1
  fi
  return 0
}

python_cmd() {
  if command -v python3 >/dev/null 2>&1; then
    echo python3
  elif command -v python >/dev/null 2>&1; then
    echo python
  else
    return 1
  fi
}

port_in_use() {
  local port="$1"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    lsof -i ":${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    ss -tlnp 2>/dev/null | grep -q ":${port} " || \
      lsof -i ":${port}" -sTCP:LISTEN >/dev/null 2>&1 || \
      netstat -tlnp 2>/dev/null | grep -q ":${port} "
  fi
}

kill_pid_gracefully() {
  local pid="$1"
  local label="$2"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  kill -TERM "$pid" 2>/dev/null || true
  local waited=0
  while kill -0 "$pid" 2>/dev/null && [[ $waited -lt 5 ]]; do
    sleep 1
    waited=$((waited + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" 2>/dev/null || true
    log_warn "${label} force-killed (PID ${pid})"
  fi
}

kill_port() {
  local port="$1"
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti ":${port}" -sTCP:LISTEN 2>/dev/null || true)"
    for pid in $pids; do
      [[ -n "$pid" ]] && kill -TERM "$pid" 2>/dev/null || true
    done
  elif command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  local exit_code=$?
  log "Shutting down DFAT services..."

  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill_pid_gracefully "$FRONTEND_PID" "Frontend"
  fi
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill_pid_gracefully "$BACKEND_PID" "Backend"
  fi

  if [[ -f "$BACKEND_PID_FILE" ]]; then
    kill_pid_gracefully "$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)" "Backend (pid file)"
    rm -f "$BACKEND_PID_FILE"
  fi
  if [[ -f "$FRONTEND_PID_FILE" ]]; then
    kill_pid_gracefully "$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)" "Frontend (pid file)"
    rm -f "$FRONTEND_PID_FILE"
  fi

  kill_port 8000 || true
  kill_port 3000 || true

  if [[ $exit_code -ne 0 ]]; then
    exit "$exit_code"
  fi
}

trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  DFAT — Digital Forensics Automation Tool                     ║"
echo "║  AI-Assisted Evidence Analysis                                ║"
echo "║  Starting local development environment...                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
PY="$(python_cmd)" || {
  log_err "ERROR: Python 3.11+ is required. Download from https://www.python.org/downloads/"
  exit 1
}

PY_VERSION="$("$PY" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  log_err "ERROR: Python 3.11+ is required (found ${PY_VERSION})."
  log_err "Download from https://www.python.org/downloads/"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  log_err "ERROR: Node.js 18+ is required. Download from https://nodejs.org/"
  exit 1
fi
NODE_VERSION="$(node --version 2>/dev/null || echo unknown)"
if ! version_compare "$NODE_VERSION" "18"; then
  log_err "ERROR: Node.js 18+ is required (found ${NODE_VERSION})."
  log_err "Download from https://nodejs.org/"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  log_err "ERROR: npm is required. Download Node.js from https://nodejs.org/"
  exit 1
fi

# ---------------------------------------------------------------------------
# First-run detection
# ---------------------------------------------------------------------------
NEED_SETUP=0
[[ -f "${ROOT}/.env" ]] || NEED_SETUP=1
[[ -d "${ROOT}/frontend/node_modules" ]] || NEED_SETUP=1
[[ -f "$DB_FILE" ]] || NEED_SETUP=1

if [[ "$NEED_SETUP" -eq 1 ]]; then
  log "First-run setup detected..."

  if [[ ! -f "${ROOT}/.env" && -f "${ROOT}/.env.example" ]]; then
    cp "${ROOT}/.env.example" "${ROOT}/.env"
    log_ok "Created .env from template"
  fi

  log "Creating data directories..."
  mkdir -p \
    "${ROOT}/data/evidence" \
    "${ROOT}/data/datasets" \
    "${ROOT}/data/outputs" \
    "${ROOT}/data/ground_truth" \
    "${ROOT}/data/questionnaire" \
    "${ROOT}/data/ml" \
    "${ROOT}/data/knowledge" \
    "${ROOT}/logs"

  USE_VENV=1
  if [[ ! -d "${ROOT}/venv" ]]; then
    START_EPOCH=$(date +%s)
    log "Creating Python virtual environment..."
    if ! "$PY" -m venv "${ROOT}/venv"; then
      log_warn "Could not create venv — installing into system Python."
      USE_VENV=0
    else
      ELAPSED=$(( $(date +%s) - START_EPOCH ))
      log_ok "Virtual environment created (${ELAPSED}s)"
    fi
  fi

  if [[ "$USE_VENV" -eq 1 ]]; then
    # shellcheck disable=SC1091
    source "${ROOT}/venv/bin/activate"
    PY=python
  fi

  START_EPOCH=$(date +%s)
  log "Installing backend dependencies..."
  if [[ "$USE_VENV" -eq 1 ]]; then
    python -m pip install -e ".[dev]" --quiet
  else
    python -m pip install -e ".[dev]" --quiet --break-system-packages
  fi
  ELAPSED=$(( $(date +%s) - START_EPOCH ))
  log_ok "Backend dependencies installed (${ELAPSED}s)"

  START_EPOCH=$(date +%s)
  log "Initialising database..."
  python -m alembic -c src/dfat/database/migrations/alembic.ini upgrade head
  ELAPSED=$(( $(date +%s) - START_EPOCH ))
  log_ok "Database initialised (${ELAPSED}s)"

  if [[ ! -d "${ROOT}/frontend/node_modules" ]]; then
    START_EPOCH=$(date +%s)
    log "Installing frontend dependencies..."
    (cd "${ROOT}/frontend" && npm install --legacy-peer-deps)
    ELAPSED=$(( $(date +%s) - START_EPOCH ))
    log_ok "Frontend dependencies installed (${ELAPSED}s)"
  fi

  # Seed requires running API
  log "Starting temporary backend for seed data..."
  PYTHONPATH="${ROOT}/src" DFAT_ENV=development PYTHONDONTWRITEBYTECODE=1 \
    python -m uvicorn dfat.app:create_app --factory --host 127.0.0.1 --port 8000 &
  SEED_PID=$!
  SEED_READY=0
  for _ in $(seq 1 60); do
    if curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
      SEED_READY=1
      break
    fi
    sleep 1
  done

  if [[ "$SEED_READY" -eq 1 ]]; then
    log "Seeding development data..."
    if python scripts/seed_dev_data.py; then
      log_ok "Development data seeded"
      echo
      echo "  Admin:        admin / Admin!Pass#2026"
      echo "  Investigator: investigator1 / Invest!Pass#2026"
      echo "  Analyst:      analyst1 / Analyst!Pass#2026"
      echo "  Viewer:       viewer1 / Viewer!Pass#2026"
      echo
    else
      log "Seed data already exists (skipping)"
    fi
  else
    log_warn "Could not reach backend for seeding — run seed manually later."
  fi

  kill_pid_gracefully "$SEED_PID" "Seed backend"
  wait "$SEED_PID" 2>/dev/null || true
  sleep 1

else
  if [[ -f "${ROOT}/venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "${ROOT}/venv/bin/activate"
    PY=python
    log_ok "Using existing environment"
  else
    log_warn "venv not found — using system Python."
  fi
fi

# ---------------------------------------------------------------------------
# Port checks
# ---------------------------------------------------------------------------
if port_in_use 8000; then
  log_warn "Port 8000 already in use. Backend may not start."
fi
if port_in_use 3000; then
  log_warn "Port 3000 already in use. Frontend may not start."
fi

# ---------------------------------------------------------------------------
# Ollama (optional)
# ---------------------------------------------------------------------------
if curl -sf http://localhost:11434/api/version >/dev/null 2>&1; then
  log_ok "Ollama detected — AI features enabled"
else
  echo "[INFO] Ollama not detected — AI will use rule-based fallback. Install from https://ollama.com for full AI features."
fi
echo

# ---------------------------------------------------------------------------
# Start backend
# ---------------------------------------------------------------------------
log "Starting backend..."
PYTHONPATH="${ROOT}/src" DFAT_ENV=development PYTHONDONTWRITEBYTECODE=1 \
  python -m uvicorn dfat.app:create_app --factory --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$BACKEND_PID_FILE"
echo "Backend starting on http://localhost:8000"

HEALTH_OK=0
for _ in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    HEALTH_OK=1
    break
  fi
  sleep 1
done

if [[ "$HEALTH_OK" -eq 1 ]]; then
  log_ok "Backend is healthy"
else
  log_warn "Backend health check timed out. Check logs for errors."
fi

# ---------------------------------------------------------------------------
# Start frontend
# ---------------------------------------------------------------------------
log "Starting frontend..."
(
  cd "${ROOT}/frontend"
  BROWSER=none npm start
) &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$FRONTEND_PID_FILE"
echo "Frontend starting on http://localhost:3000"

sleep 5
python scripts/open_browser.py \
  --url http://localhost:3000 \
  --health-url http://localhost:8000/api/v1/health \
  --timeout 60 || true

echo
echo "════════════════════════════════════════════════════════════"
echo "  DFAT is running!"
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo "  Health:    http://localhost:8000/api/v1/health"
echo
echo "  Login with: admin / Admin!Pass#2026"
echo
echo "  To stop: press Ctrl+C in this terminal, or run ./stop.sh"
echo "════════════════════════════════════════════════════════════"
echo

# Disable EXIT trap cleanup killing on normal wait — we want Ctrl+C to cleanup
wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
