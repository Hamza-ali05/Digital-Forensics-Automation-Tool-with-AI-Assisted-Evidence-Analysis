#!/bin/bash
# Initialise the DFAT database via Alembic migrations.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

mkdir -p data
export PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"

echo "Running Alembic migrations..."
alembic -c src/dfat/database/migrations/alembic.ini upgrade head
echo "Database initialised successfully."
