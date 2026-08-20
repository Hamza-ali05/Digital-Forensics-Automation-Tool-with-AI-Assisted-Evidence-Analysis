# DFAT System Architecture

DFAT (Digital Forensics Automation Tool with AI-Assisted Evidence Analysis) is a local-first digital-forensics platform developed as an MSc Cybersecurity research artefact at Canterbury Christ Church University. The architecture is organized around a five-stage forensic pipeline, a layered service design, explicit chain-of-custody controls, and a local-only AI analysis subsystem.

Related architecture documents:

- Pipeline internals: [`PIPELINE.md`](PIPELINE.md)
- AI engine: [`AI_ENGINE.md`](AI_ENGINE.md)
- Reporting: [`REPORTING.md`](REPORTING.md)
- Evaluation: [`EVALUATION.md`](EVALUATION.md)
- ADR index: [`adr/README.md`](adr/README.md)
- Component catalogue: [`COMPONENT_CATALOGUE.md`](COMPONENT_CATALOGUE.md)

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ Investigator / Administrator Workstation                                           │
│  Browser -> React UI -> Dashboard / Cases / Evidence / Pipeline / AI / Reports    │
└──────────────────────────────────────┬──────────────────────────────────────────────┘
                                       │ HTTP(S) /api/v1
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ Presentation Layer                                                                 │
│  FastAPI routes · Pydantic DTOs · auth middleware · validation · monitoring        │
│  Modules: src/dfat/api/, frontend/src/pages/                                       │
└───────────────────────┬───────────────────────────────┬─────────────────────────────┘
                        │                               │
                        ▼                               ▼
┌──────────────────────────────────┐   ┌─────────────────────────────────────────────┐
│ Application Layer                │   │ Five-Stage Pipeline                         │
│ Services · DI container · RBAC   │   │ Acquisition -> Parsing -> AI Triage ->     │
│ Case/Evidence/Analysis/Report    │   │ Reporting -> Evaluation                     │
│ Evaluation/User/Audit services   │   │ JobManager · JobRunner · StageRegistry      │
└──────────────────┬───────────────┘   └──────────────────────┬──────────────────────┘
                   │                                          │
                   ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ Domain Layer                                                                       │
│  Models · enums · repository/parser/analyzer/evaluator/reporter interfaces         │
│  ArtefactSet · CaseMetadata · BenchmarkResult · UsabilityResponse                  │
└───────────────────────┬─────────────────────────────────────────────────────────────┘
                        │ adapters
                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ Infrastructure + Engines                                                           │
│  Forensic engine · AI engine · reporting engine · evaluation engine                │
│  SQLAlchemy repositories · LocalFileStorage · SecureStorage · Audit logger         │
│  Ollama client · JSON exporter · narrative assembler · benchmark comparator        │
└──────────────┬───────────────────────────┬──────────────────────┬───────────────────┘
               │                           │                      │
               ▼                           ▼                      ▼
       ┌───────────────┐          ┌────────────────┐     ┌────────────────────┐
       │ SQLite /      │          │ Evidence /     │     │ Ollama local LLM   │
       │ PostgreSQL    │          │ Report storage │     │ llama3 via :11434  │
       │ metadata DB   │          │ on local disk  │     │ local-only         │
       └───────────────┘          └────────────────┘     └────────────────────┘
```

Evidence files remain on disk; the database stores metadata, jobs, users, audit entries, benchmark results, and report references rather than raw forensic blobs.

## Technology Stack

| Area | Technology |
|------|------------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic 2.0 |
| Frontend | React 17+, React Bootstrap, Volt Dashboard, Chart.js |
| Forensics | pytsk3, python-registry, Volatility3, python-evtx |
| AI | LLaMA-3 via Ollama (local only) |
| Database | SQLite (development) / PostgreSQL (production option) |
| Auth | JWT, RBAC, password hashing |
| Reports | JSON, narrative, PDF, HTML |
| Testing | pytest, Jest, Playwright |
| Packaging / Ops | Docker, Nginx, GitHub Actions |

## Five-Stage Pipeline

The DFAT core workflow is a five-stage pipeline coordinated by `PipelineOrchestrator` and executed through `JobManager`, `JobRunner`, and stage-specific classes in `src/dfat/pipeline/stages/`.

### Stage 1 — Acquisition

- **Input:** evidence identifier, file path, case metadata
- **Output:** loaded `EvidenceImage` plus verified integrity metadata
- **Components:** `DiskImageHandler`, `MemoryDumpHandler`, `IntegrityChecker`, `ChainOfCustodyService`
- **Responsibility:** load evidence, verify hashes, register custody events, prepare inputs for parsing

### Stage 2 — Parsing

- **Input:** acquired evidence image or memory dump
- **Output:** parser-specific `ArtefactSet` objects merged into one normalized `ArtefactSet`
- **Components:** `ParserRegistry`, `ForensicOrchestrator`, `ArtefactNormalizer`, parser modules in `src/dfat/forensic_engine/parsers/`
- **Responsibility:** route by evidence type, extract artefacts, normalize heterogeneous parser outputs

### Stage 3 — AI Triage

- **Input:** normalized artefact set
- **Output:** scored, ranked, classified artefacts plus optional AI summary metadata
- **Components:** `IOCDetector`, `ArtefactCorrelator`, `TimelineGenerator`, `ScoringEngine`, `RuleBasedTriageEngine`, `LocalLLMClient`, `RuleBasedAnalyzer`
- **Responsibility:** correlate artefacts, detect indicators, compute suspicion levels, enrich results with local LLM when available

### Stage 4 — Reporting

- **Input:** ranked artefacts, case metadata, stage timings, AI metadata
- **Output:** structured JSON report and narrative report
- **Components:** `StructuredJSONExporter`, `NarrativeAssembler`, `DualOutputReportBuilder`, `PDFReportExporter`, `HTMLReportExporter`
- **Responsibility:** generate evidential JSON, produce advisory narrative, preserve reproducibility metadata, support export

### Stage 5 — Evaluation

- **Input:** recovered artefacts, ground truth, pipeline timing data
- **Output:** `BenchmarkResult`, performance report, usability-analysis outputs where applicable
- **Components:** `GroundTruthLoader`, `MetricsCalculator`, `BenchmarkComparator`, `PerformanceAnalyzer`, `QuestionnaireInstrument`, `ResponseAnalyzer`
- **Responsibility:** measure artefact-recovery accuracy, time-to-triage, and investigator usability

## Data Flow Diagram

```text
Evidence file
  -> Acquisition
  -> Parsing
  -> Normalisation
  -> Correlation
  -> IOC Detection
  -> Scoring
  -> Triage
  -> Classification
  -> Ranking
  -> Summarisation
  -> JSON Export
  -> Narrative
  -> Report
  -> Evaluation
```

## Layered Architecture

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION                                                            │
│ React UI · FastAPI routes · API schemas · middleware                    │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────────┐
│ APPLICATION                                                             │
│ Services · Pipeline orchestration · dependency injection                │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────────┐
│ DOMAIN                                                                  │
│ Models · enums · ports/interfaces · exceptions                          │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────────┐
│ INFRASTRUCTURE / ENGINE ADAPTERS                                        │
│ Repositories · storage · audit logging · Ollama client · exporters      │
└──────────────────────────────────────────────────────────────────────────┘
```

Cross-cutting middleware order on the request path:

`RequestID -> Compression -> SecurityHeaders -> RateLimiter -> CORS -> ResponseCache -> AuditTrail -> RequestValidation -> routes -> GlobalExceptionHandler`

## Component Catalogue

The complete catalogue is maintained in [`COMPONENT_CATALOGUE.md`](COMPONENT_CATALOGUE.md). The table below lists the principal architectural anchors.

| Class / Component | Module | Prompt of Origin | Interface / Role |
|------------------|--------|------------------|------------------|
| `ApplicationContainer` | `src/dfat/container.py` | 1-3 | DI composition root |
| `ParserRegistry` | `src/dfat/pipeline/parser_registry.py` | 4 | parser registry / `IArtefactParser` consumer |
| `ForensicOrchestrator` | `src/dfat/forensic_engine/orchestrator.py` | 4 | evidence routing + parser execution |
| `ArtefactNormalizer` | `src/dfat/forensic_engine/normalizer.py` | 4 | normalized `ArtefactSet` producer |
| `PipelineOrchestrator` | `src/dfat/pipeline/__init__.py` / `orchestrator` | 4 | pipeline coordinator |
| `LocalLLMClient` | `src/dfat/ai_engine/analyzer.py` | 5 | AI analysis client |
| `LLMConnectionManager` | `src/dfat/ai_engine/llm/connection.py` | 5 | local-only Ollama enforcement |
| `HallucinationGuard` | `src/dfat/ai_engine/validation/hallucination_guard.py` | 5 | hallucination mitigation |
| `RuleBasedAnalyzer` | `src/dfat/ai_engine/fallback/rule_based.py` | 5 | fallback analyzer / `IArtefactAnalyzer` |
| `StructuredJSONExporter` | `src/dfat/reporting/json_layer.py` | 6 | evidential JSON exporter |
| `NarrativeAssembler` | `src/dfat/reporting/narrative.py` | 6 | advisory narrative assembler |
| `DualOutputReportBuilder` | `src/dfat/reporting/report_builder.py` | 6 | report generation / `IReportGenerator` |
| `GroundTruthLoader` | `src/dfat/evaluation/benchmark/ground_truth.py` | 6 | benchmark dataset loader |
| `MetricsCalculator` | `src/dfat/evaluation/benchmark/metrics.py` | 6 | benchmark metrics |
| `BenchmarkComparator` | `src/dfat/evaluation/benchmark/comparator.py` | 6 | TP/FP/FN comparison |
| `QuestionnaireInstrument` | `src/dfat/evaluation/usability/questionnaire.py` | 6 | usability instrument |
| `ResponseAnalyzer` | `src/dfat/evaluation/usability/response_analyzer.py` | 6 | questionnaire analysis |
| `ResponseCollector` | `src/dfat/evaluation/usability/response_collector.py` | 6 | anonymized response collection |

## Security Architecture

### Authentication Flow

1. User authenticates via `auth` routes.
2. Backend validates credentials and issues JWT tokens.
3. Protected routes require authenticated user context.
4. Role checks are enforced through RBAC dependencies.

### RBAC Model

Roles implemented in the system:

- `admin`
- `investigator`
- `analyst`
- `viewer`

Source of truth:
- `src/dfat/auth/rbac.py`
- `src/dfat/api/dependencies.py`

### Audit Trail

Auditability is a first-class architectural concern:

- API middleware captures security-relevant actions
- forensic pipeline stages emit audit events
- evidence handling preserves chain-of-custody semantics
- usability deletion actions are also audited for ethics compliance

Key components:
- `ForensicAuditLogger`
- `AuditService`
- `AuditTrailMiddleware`

### Chain-of-Custody

Evidence custody is treated as append-only. Registration, transfer, validation, acquisition, and quarantine actions all contribute to a traceable custody record.

## Deployment Architecture

### Production Topology

```text
Client Browser
  -> Nginx reverse proxy (:80/:443)
      -> Frontend container
      -> Backend FastAPI container
          -> SQLite / PostgreSQL metadata store
          -> local evidence/report/audit volumes
          -> Ollama container (:11434)
```

### Docker Services

- `backend`
- `frontend`
- `nginx`
- `ollama`

### Volume Mounts

- evidence data volume
- report output volume
- audit log volume
- database volume
- Ollama model volume

### Operational Documents

- deployment guide: `deploy/README.md`
- production compose: `deploy/docker-compose.production.yml`
- Nginx config: `deploy/nginx/nginx.conf`
- backup / restore: `deploy/scripts/backup.sh`, `deploy/scripts/restore.sh`

## ADR Index

| ADR | Title | Prompt | Status |
|-----|-------|--------|--------|
| [001](adr/ADR-001-design-science-research.md) | DSR Methodology | 1 | Accepted |
| [002](adr/ADR-002-local-llm-only.md) | Local LLM Only | 1 | Accepted |
| [003](adr/ADR-003-dual-output-report.md) | Dual-Output Report Format | 1 | Accepted |
| [004](adr/ADR-004-file-based-repositories.md) | Repository Pattern with File-Based Storage | 1 | Accepted |
| [005](adr/ADR-005-graceful-forensic-deps.md) | Graceful Degradation on Library Absence | 1 | Accepted |
| [006](adr/ADR-006-rule-based-fallback.md) | Rule-Based Fallback Analyzer | 1 | Accepted |
| [007](adr/ADR-007-sqlalchemy-async-persistence.md) | SQLAlchemy Async Persistence | 2 | Accepted |
| [008](adr/ADR-008-jwt-rbac.md) | JWT Authentication with RBAC | 2 | Accepted |
| [009](adr/ADR-009-service-layer.md) | Service Layer Pattern | 2 | Accepted |
| [010](adr/ADR-010-case-lifecycle-management.md) | Case Lifecycle Management | 3 | Accepted |
| [011](adr/ADR-011-multi-algorithm-hashing.md) | Multi-Algorithm Hashing | 3 | Accepted |
| [012](adr/ADR-012-chain-of-custody-immutability.md) | Chain-of-Custody Immutability | 3 | Accepted |
| [013](adr/ADR-013-parser-lazy-imports.md) | Lazy Forensic Library Imports | 4 | Accepted |
| [014](adr/ADR-014-graceful-parser-degradation.md) | Graceful Parser Degradation | 4 | Accepted |
| [015](adr/ADR-015-artefact-raw-data-contracts.md) | Artefact `raw_data` Contracts | 4 | Accepted |
| [016](adr/ADR-016-rule-based-triage-first.md) | Rule-Based Triage First | 4 | Accepted |
| [017](adr/017-local-llm-only.md) | Local LLM Only (Prompt 5) | 5 | Accepted |
| [018](adr/018-hallucination-mitigation.md) | Hallucination Mitigation | 5 | Accepted |
| [019](adr/019-prompt-versioning.md) | Prompt Versioning | 5 | Accepted |
| [020](adr/020-rule-based-triage-primary.md) | Rule-Based Triage Primary | 5 | Accepted |
| [021](adr/021-json-layer-primary-record.md) | JSON Layer as Primary Evidential Record | 6 | Accepted |
| [022](adr/022-report-schema-versioning.md) | Report Schema Versioning | 6 | Accepted |
| [023](adr/023-questionnaire-immutability.md) | Questionnaire Instrument Immutability | 6 | Accepted |
| [024](adr/024-tobin-comparability.md) | Tobin Comparability | 6 | Accepted |

## Verification Cross-Reference

The final architecture is supported by:

- `scripts/verify_research_objectives.py`
- `scripts/verify_features.py`
- `scripts/verify_dsr_methodology.py`
- `reports/research_objectives_verification.json`
- `reports/feature_verification.json`
- `reports/dsr_verification.json`
