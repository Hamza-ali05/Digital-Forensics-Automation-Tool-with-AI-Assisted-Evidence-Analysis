# DFAT — Digital Forensics Automation Tool

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-18%2B-green)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)](http://127.0.0.1:8000/docs)
[![Mypy](https://img.shields.io/badge/mypy-strict-blue)](#)
[![Tests](https://img.shields.io/badge/tests-pytest%20%7C%20jest%20%7C%20playwright-success)](#)

**DFAT** (Digital Forensics Automation Tool with AI-Assisted Evidence Analysis)
is a local-first platform that takes forensic disk images and memory dumps
through a five-stage pipeline: acquisition, artefact parsing, AI-assisted
triage (local LLaMA-3 via Ollama), dual-output reporting, and benchmark
evaluation against DFRWS/CFReDS ground truth.

The system is an MSc Cybersecurity research artefact. Inference never leaves
the investigator’s machine. Structured JSON is the evidential record; LLM
narrative is advisory.

## Architecture

```text
Investigator UI (React :3000)
        │  /api/v1  JWT + RBAC
        ▼
FastAPI (:8000) ──▶ services ──▶ domain (core)
        │                         │
        │     ┌───────────────────┼───────────────────┐
        ▼     ▼                   ▼                   ▼
   SQLite/PG   audit JSONL    Ollama llama3      evidence files
                              (localhost)

Pipeline:  Acquisition → Parsing → AI Triage → Reporting → Evaluation
```

Full diagrams, layering, and the 24-ADR index:
[docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md).

## Features

- **Case lifecycle** — create → open → active → review → close → archive, with
  investigator assignment and access control.
- **Evidence management** — server-side registration, multi-algorithm hashing
  (SHA-256 primary), MIME/format validation, quarantine, append-only chain of
  custody.
- **Artefact parsers** — disk (filesystem, registry, browser, event log) and
  memory (processes, network, injection, registry); graceful skip when native
  libraries are missing.
- **Rule-first triage** — deterministic scoring and IOC rules, optional local
  LLM classification, summarisation, explanation, and investigator Q&A.
- **Dual-output reports** — versioned JSON (primary) plus narrative; PDF, HTML,
  and JSON file export; integrity verify and reproducibility compare.
- **Evaluation** — DFRWS/CFReDS precision/recall/F1 and time-to-triage;
  immutable SUS-style usability questionnaire.
- **Security** — local JWT, four roles (admin / investigator / analyst /
  viewer), rate limits, security headers, path-traversal guards, audit dual-write.
- **Operations** — health/readiness aggregator, request IDs, Alembic migrations,
  Docker Compose for lab stacks.

## Quick start

Follow the ten-step guide:

**[docs/user-guide/QUICKSTART.md](docs/user-guide/QUICKSTART.md)**

Prerequisites: Python 3.11+, Node.js 18+, Ollama (`ollama pull llama3`).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev,auth,reporting]"
make frontend-install
make db-init
make dev-backend                   # terminal 1
make seed-dev                      # terminal 2 (API must be up)
make dev-frontend                  # terminal 3
```

UI: http://127.0.0.1:3000 — login `admin` / `Admin!Pass#2026`  
API docs: http://127.0.0.1:8000/docs

Docker lab stack: `docker compose -f docker-compose.dev.yml up --build`.

## Documentation index

| Document | Contents |
|----------|----------|
| [User quick start](docs/user-guide/QUICKSTART.md) | Install, seed, first case → pipeline → results |
| [User manual](docs/user-guide/USER_MANUAL.md) | Every UI workflow, roles, questionnaire, admin |
| [Architecture](docs/architecture/ARCHITECTURE.md) | System diagram, pipeline, layers, stack, ADR index |
| [Pipeline](docs/architecture/PIPELINE.md) | Stages, parsers, `raw_data` contracts |
| [AI engine](docs/architecture/AI_ENGINE.md) | Local LLM, fallback, prompts |
| [Reporting](docs/architecture/REPORTING.md) | Dual-output reports |
| [Evaluation](docs/architecture/EVALUATION.md) | Benchmarks and usability |
| [API reference](docs/development/API_REFERENCE.md) | Every `/api/v1` endpoint |
| [Pipeline API](docs/api/PIPELINE_API.md) | Job submission examples |
| [Developer guide](docs/development/DEVELOPER_GUIDE.md) | Parsers, rules, reports, endpoints, tests |
| [Coding standards](docs/development/CODING_STANDARDS.md) | Python style and boundaries |
| [Git workflow](docs/development/GIT_WORKFLOW.md) | Branches and Conventional Commits |
| [Deployment](docs/deployment/DEPLOYMENT.md) | Docker, env vars, TLS, backup, monitoring |
| [ADRs](docs/architecture/adr/README.md) | 24 architecture decision records |
| [Frontend pages](frontend/PAGES.md) | Route ↔ permission ↔ API map |

## Research context

DFAT is submitted as postgraduate research for the **MSc Cybersecurity** at
**Canterbury Christ Church University (CCCU)**. The work follows **Design
Science Research** (Hevner et al., 2004): build a working artefact, then
evaluate it with forensic benchmarks (DFRWS / CFReDS) and a locked usability
instrument comparable to Tobin et al. Design choices favour reproducibility,
ACPO-oriented audit, and GDPR-compatible **local-only** inference over
cloud-scale operations ([ADR-001](docs/architecture/adr/ADR-001-design-science-research.md)).

## Acknowledgments

Supervised by **Dr. Mandy Qi**, Canterbury Christ Church University (CCCU).

Developed as postgraduate research at CCCU. Contact on the API OpenAPI
metadata: Muhammad Aaqif Afzaal (`100176885@canterbury.ac.uk`).

## License

[MIT License](LICENSE) — Copyright (c) 2026 DFAT Contributors.
