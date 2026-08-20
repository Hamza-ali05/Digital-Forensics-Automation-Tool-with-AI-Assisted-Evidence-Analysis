#!/usr/bin/env bash
# DFAT graceful shutdown for macOS / Linux.
# Make executable: chmod +x stop.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID_FILE="${ROOT}/.dfat_backend.pid"
FRONTEND_PID_FILE="${ROOT}/.dfat_frontend.pid"

kill_pid_gracefully() {
  local pid="$1"
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
  fi
}

kill_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti ":${port}" -sTCP:LISTEN 2>/dev/null | while read -r pid; do
      kill -TERM "$pid" 2>/dev/null || true
    done
  elif command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  fi
}

if [[ -f "$BACKEND_PID_FILE" ]]; then
  kill_pid_gracefully "$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)"
  rm -f "$BACKEND_PID_FILE"
fi

if [[ -f "$FRONTEND_PID_FILE" ]]; then
  kill_pid_gracefully "$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)"
  rm -f "$FRONTEND_PID_FILE"
fi

kill_port 8000 || true
kill_port 3000 || true

echo "DFAT stopped."
