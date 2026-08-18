# DFAT System Architecture

DFAT (Digital Forensics Automation Tool with AI-Assisted Evidence Analysis) is a
local-first, five-stage forensic processing system. It is an MSc Cybersecurity
research artefact at Canterbury Christ Church University (CCCU), built under
Design Science Research (DSR) constraints: evaluability, reproducibility, and
chain-of-custody accountability over cloud scale.

Related documents:

- Pipeline internals: [`PIPELINE.md`](PIPELINE.md)
- AI engine: [`AI_ENGINE.md`](AI_ENGINE.md)
- Reporting: [`REPORTING.md`](REPORTING.md)
- Evaluation: [`EVALUATION.md`](EVALUATION.md)
- ADRs: [`adr/README.md`](adr/README.md)

## System overview

```text
                         ┌─────────────────────────────────────────┐
                         │         Investigator workstation        │
                         │  Browser ──▶ React UI (:3000)           │
                         └──────────────────┬──────────────────────┘
                                            │ HTTP /api/v1
                                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ FastAPI presentation layer (:8000)                                       │
│  Auth · Cases · Evidence · Pipeline · AI · Reports · Evaluation · Health │
│  JWT + RBAC · audit middleware · rate limit · security headers           │
└──────────────────┬───────────────────────────────┬───────────────────────┘
                   │                               │
                   ▼                               ▼
┌────────────────────────────────┐   ┌─────────────────────────────────────┐
│ Application services           │   │ Five-stage pipeline orchestrator    │
│ Case / Evidence / Analysis /   │   │ acquisition → parsing → ai_triage   │
│ Report / Evaluation / User     │   │ → reporting → evaluation            │
└────────────────┬───────────────┘   └──────────────────┬──────────────────┘
                 │                                      │
                 ▼                                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Domain (src/dfat/core) — models, enums, ports, exceptions                │
└──────────────────────────────────────────────────────────────────────────┘
                 │
     ┌───────────┼───────────────┬──────────────────┐
     ▼           ▼               ▼                  ▼
┌─────────┐ ┌─────────┐ ┌─────────────────┐ ┌────────────────┐
│ SQLite /│ │ Local   │ │ Ollama (local   │ │ File storage   │
│ Postgres│ │ audit   │ │ LLaMA-3 only)   │ │ evidence +     │
│ metadata│ │ JSONL   │ │ :11434          │ │ reports        │
└─────────┘ └─────────┘ └─────────────────┘ └────────────────┘
```

Evidence **files** stay on disk. The database stores metadata, users, jobs,
artefacts, reports, and audit rows — never raw forensic blobs.

## Five-stage pipeline

Jobs are submitted asynchronously (`POST /api/v1/pipeline/run`, HTTP 202).
Stages implement `IPipelineStage` and share a `PipelineContext`. Enum values
live on `PipelineStage` in `src/dfat/core/enums.py`.

```text
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ 1.Acquire   │──▶│ 2.Parsing   │──▶│ 3.AI Triage │──▶│ 4.Reporting │──▶│ 5.Evaluate  │
│ acquisition │   │ parsing     │   │ ai_triage   │   │ reporting   │   │ evaluation  │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
  hash + custody    disk/memory       rule-first +      JSON (primary)     DFRWS/CFReDS
  → ACQUIRED        parsers →         optional LLM      + narrative        (non-blocking)
                    ArtefactSet       ranked triage
```

| Stage | Enum | Responsibility |
|-------|------|----------------|
| Acquisition | `acquisition` | Load evidence metadata, verify integrity hashes, advance chain-of-custody |
| Parsing | `parsing` | Route by evidence type to registered parsers; emit a normalised `ArtefactSet` |
| AI Triage | `ai_triage` | Correlate, timeline, IOC detect, score; **rule-based first**, local LLM when available |
| Reporting | `reporting` | Dual-output forensic report: structured JSON (evidential) + narrative (advisory) |
| Evaluation | `evaluation` | Optional benchmark metrics against local ground truth; failure does not abort the job |

Job modes:

| Mode | Stages |
|------|--------|
| `full` | 1 → 5 |
| `parse-only` | Acquisition + Parsing |
| `triage-only` | Assumes artefacts exist; runs triage (and reporting when configured) |

Parsers degrade when optional forensic libraries (`pytsk3`, Volatility3, and so on)
are missing: the job continues with remaining parsers ([ADR-014](adr/ADR-014-graceful-parser-degradation.md)).

## Layer diagram

Clean architecture with a strict inward dependency rule: **domain depends on
nothing**; engines and infrastructure depend on domain ports.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION                                                            │
│  React (CRA 3.4, Bootstrap 5) · FastAPI routes · Pydantic request/resp  │
│  src/dfat/api/  ·  frontend/src/pages/                                  │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ DTOs, JWT, RBAC
┌─────────────────────────────────▼───────────────────────────────────────┐
│ APPLICATION                                                             │
│  Services (Case, Evidence, Analysis, Report, Evaluation, User, Audit)   │
│  PipelineOrchestrator · dependency-injector container                   │
│  src/dfat/services/  ·  src/dfat/container.py  ·  src/dfat/pipeline/    │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ domain models / ports
┌─────────────────────────────────▼───────────────────────────────────────┐
│ DOMAIN                                                                  │
│  Artefact, Evidence, Case, ForensicReport, enums, exceptions            │
│  Ports: IArtefactParser, IReportGenerator, IAnalyzer                    │
│  src/dfat/core/                                                         │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ adapters
┌─────────────────────────────────▼───────────────────────────────────────┐
│ INFRASTRUCTURE                                                          │
│  SQLAlchemy async repositories · Alembic · LocalFileStorage             │
│  ForensicAuditLogger (JSONL) · Ollama HTTP client · SecureStorage       │
│  src/dfat/database/  ·  src/dfat/infrastructure/  ·  src/dfat/auth/     │
└─────────────────────────────────────────────────────────────────────────┘
```

Cross-cutting middleware (outermost → innermost on the request path):
`RequestID` → `Compression` → `SecurityHeaders` → `RateLimiter` → CORS →
`ResponseCache` → `AuditTrail` → `RequestValidation` → routes /
`GlobalExceptionHandler`.

## Technology stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ (backend), Node.js 18+ (frontend) |
| HTTP API | FastAPI, Uvicorn, Pydantic v2 |
| Auth | JWT (HS256), Argon2/passlib, local RBAC (`admin`, `investigator`, `analyst`, `viewer`) |
| Persistence | SQLAlchemy 2 async, Alembic; SQLite (`aiosqlite`) default, PostgreSQL (`asyncpg`) optional |
| DI | `dependency-injector` (`ApplicationContainer`) |
| Config | YAML (`config/default.yaml` + `{env}.yaml`) overlayed by `DFAT_*` env vars |
| Pipeline | `PipelineOrchestrator`, five `IPipelineStage` implementations |
| Parsers | pytsk3, python-registry, python-evtx, Volatility3 (all optional) |
| AI | Local Ollama HTTP API, default model `llama3` — no cloud inference |
| Reports | Dual JSON + narrative; exporters for JSON file, HTML (Jinja2), PDF (ReportLab) |
| Frontend | React 16, React Router 5, Bootstrap 5 / Themesberg Volt, Axios |
| Tests | pytest (unit / integration / contract / security / validation / regression), Jest, Playwright |
| Packaging | `pyproject.toml` extras: `dev`, `forensic`, `auth`, `reporting`, `production` |

## Roles and permissions

| Role | Cases | Evidence | Analysis / pipeline / AI | Reports | Evaluation | Users / system |
|------|-------|----------|--------------------------|---------|------------|----------------|
| `admin` | full | full | full | full | full | full |
| `investigator` | create / read / update | full | create / read | create / read | create / read | — |
| `analyst` | read | read | create / read | read | read | — |
| `viewer` | — | — | — | read | read | — |

Source of truth: `src/dfat/auth/rbac.py` (`ROLE_PERMISSIONS`).

## ADR index (Prompts 1–6)

All 24 Architecture Decision Records:

| ADR | Title | Decision in one line |
|-----|-------|----------------------|
| [ADR-001](adr/ADR-001-design-science-research.md) | Design Science Research Methodology | Treat DFAT as a DSR artefact: evaluability over enterprise scale |
| [ADR-002](adr/ADR-002-local-llm-only.md) | Local LLM Only — No Cloud Inference | All inference stays on a local LLM endpoint |
| [ADR-003](adr/ADR-003-dual-output-report.md) | Dual-Output Report Format | JSON evidential record plus human-readable narrative |
| [ADR-004](adr/ADR-004-file-based-repositories.md) | Repository Pattern with File-Based Storage | Evidence and report files on disk behind repository ports |
| [ADR-005](adr/ADR-005-graceful-forensic-deps.md) | Graceful Degradation on Library Absence | Optional forensic libraries must not crash the process |
| [ADR-006](adr/ADR-006-rule-based-fallback.md) | Rule-Based Fallback Analyzer | When the LLM is down, continue with deterministic rules |
| [ADR-007](adr/ADR-007-sqlalchemy-async-persistence.md) | SQLAlchemy Async Persistence | Async SQLAlchemy for metadata, users, jobs, and audit |
| [ADR-008](adr/ADR-008-jwt-rbac.md) | JWT Authentication with RBAC | Local JWT + four forensic roles |
| [ADR-009](adr/ADR-009-service-layer.md) | Service Layer Pattern | Application services sit between routes and repositories |
| [ADR-010](adr/ADR-010-case-lifecycle-management.md) | Case Lifecycle Management | Explicit case status machine with audit |
| [ADR-011](adr/ADR-011-multi-algorithm-hashing.md) | Multi-Algorithm Hashing | SHA-256 primary with MD5 (and SHA-1 available) |
| [ADR-012](adr/ADR-012-chain-of-custody-immutability.md) | Chain-of-Custody Immutability | Append-only custody records; never rewrite history |
| [ADR-013](adr/ADR-013-parser-lazy-imports.md) | Lazy Forensic Library Imports | Import pytsk3 / Volatility only when a parser runs |
| [ADR-014](adr/ADR-014-graceful-parser-degradation.md) | Graceful Parser Degradation | Unavailable parsers are skipped, not fatal |
| [ADR-015](adr/ADR-015-artefact-raw-data-contracts.md) | Artefact `raw_data` Contracts | Category-specific dict schemas for artefacts |
| [ADR-016](adr/ADR-016-rule-based-triage-first.md) | Rule-Based Triage First | Deterministic scoring/rules run before LLM enrichment |
| [ADR-017](adr/017-local-llm-only.md) | Local LLM Only (Prompt 5) | Enforce localhost-only Ollama URLs in the client |
| [ADR-018](adr/018-hallucination-mitigation.md) | Hallucination Mitigation | Validate LLM output against artefact evidence |
| [ADR-019](adr/019-prompt-versioning.md) | Prompt Versioning | Stamp prompt version on AI analysis records |
| [ADR-020](adr/020-rule-based-triage-primary.md) | Rule-Based Triage Primary | Rules remain the primary triage path |
| [ADR-021](adr/021-json-layer-primary-record.md) | JSON Layer as Primary Evidential Record | Narrative is advisory; JSON is the record |
| [ADR-022](adr/022-report-schema-versioning.md) | Report Schema Versioning | Versioned JSON schema for forensic reports |
| [ADR-023](adr/023-questionnaire-immutability.md) | Questionnaire Instrument Immutability | Ethics-locked usability instrument cannot be edited at runtime |
| [ADR-024](adr/024-tobin-comparability.md) | Tobin et al. Comparability | Usability metrics remain comparable to Tobin et al. |

The catalogue index is also maintained in [`adr/README.md`](adr/README.md).
