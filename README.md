# DFAT — Digital Forensics Automation Tool

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pending-lightgrey)](#)
[![Mypy](https://img.shields.io/badge/mypy-strict-blue)](#)

DFAT (Digital Forensics Automation Tool with AI-Assisted Evidence Analysis) is an MSc Cybersecurity research project that implements a local-first forensic evidence processing pipeline spanning five stages: Acquisition, Artefact Parsing, AI Triage/NLP (local LLaMA-3), Dual-Output Reporting, and Benchmark Evaluation against DFRWS/CFReDS ground truth.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
# Optional forensic libraries:
pip install -e ".[forensic]"
```

Or use the helper script:

```bash
bash scripts/setup_dev.sh
```

## Quickstart

```bash
python -m dfat
make run-api
# API docs: http://127.0.0.1:8000/docs
```

## Pipeline

DFAT runs a five-stage forensic pipeline: **Acquisition → Parsing → AI Triage →
Reporting → Evaluation**. Jobs are submitted asynchronously via the API and can
run in `full`, `parse-only`, or `triage-only` mode. Parsers degrade gracefully
when optional forensic libraries are missing; triage prefers rule-based scoring
with optional local LLM enrichment.

```bash
# Example: submit a full pipeline job (requires JWT)
curl -X POST http://127.0.0.1:8000/api/v1/pipeline/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"evidence_id":"<id>","case_id":"<id>","mode":"full"}'
```

| Doc | Description |
|-----|-------------|
| [`docs/architecture/PIPELINE.md`](docs/architecture/PIPELINE.md) | Stages, parsers, `raw_data` contracts, config, errors |
| [`docs/api/PIPELINE_API.md`](docs/api/PIPELINE_API.md) | HTTP endpoints with request/response examples |
| [ADR-013–016](docs/architecture/adr/README.md) | Lazy imports, degradation, contracts, rule-first triage |

```bash
make test-pipeline   # pipeline + processing unit/integration tests
make test-parsers    # artefact parser unit tests
make test-prompt4    # Prompt 4 suite aggregate
```

## Project Structure

```
dfat/
├── src/dfat/           # Application packages (domain, engines, API, infrastructure)
│   ├── pipeline/       # Orchestrator, stages, job/progress models
│   └── forensic_engine/parsers/  # Disk + memory artefact parsers
├── tests/              # Unit, integration, and fixture data
├── config/             # Hierarchical YAML configuration
├── docs/               # Architecture, API, user, and development docs
├── scripts/            # Developer setup and utility scripts
└── data/               # Runtime evidence/outputs (gitignored)
```

## License

MIT License.

## Acknowledgments

Developed as postgraduate research at Canterbury Christ Church University (CCCU), with supervisory acknowledgment to Dr. Mandy Qi.
