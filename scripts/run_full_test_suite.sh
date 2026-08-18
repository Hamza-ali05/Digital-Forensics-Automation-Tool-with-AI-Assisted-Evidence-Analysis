#!/usr/bin/env bash
# Run every DFAT test category in order and emit combined coverage.
# Order: unit → integration → contract → security → validation →
#        regression → performance → frontend unit → E2E
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  PYTHON=python3
fi

exec "${PYTHON}" scripts/run_full_test_suite.py "$@"
