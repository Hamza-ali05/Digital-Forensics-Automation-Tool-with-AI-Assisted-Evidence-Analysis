#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -U pip
pip install -e ".[dev,forensic]"
pre-commit install

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

mkdir -p \
  data/evidence \
  data/outputs \
  data/datasets \
  data/ground_truth \
  data/questionnaire/responses

echo "DFAT development environment ready."
