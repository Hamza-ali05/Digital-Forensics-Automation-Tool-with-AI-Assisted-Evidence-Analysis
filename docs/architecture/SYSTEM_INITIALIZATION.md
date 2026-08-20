# System Initialization

DFAT starts through `BootSequencer`, which coordinates every Prompt 12
initialiser in dependency order and emits a `StartupReport` consumed by the API
(`/api/v1/system/startup`), the frontend startup screen, and
`scripts/verify_system_initialization.py`.

## Dependency Graph

```text
CONFIGURATION
    └─► DIRECTORIES
            └─► DATABASE ──────────────────────────────┐
                    └─► AUTHENTICATION                 │
                            └─► AUDIT_LOGGING          │
                                    │                  │
                    ┌───────────────┴───────────────┐  │
                    ▼                               ▼  │
            FORENSIC_PARSERS              DATASET_DISCOVERY
                    │                               │
                    │                     KNOWLEDGE_BASE
                    │                               │
                    │                     IOC_DATABASE
                    │                               │
                    │                     THREAT_INTELLIGENCE
                    │                               │
                    │                     ML_MODELS
                    │                               │
                    │                     LLM_SERVICE
                    │                               │
                    │                     RAG_PIPELINE
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                              REPORTING (critical)
                                    │
                              EVALUATION
                                    │
                              BACKGROUND_WORKERS
```

Critical phases (abort on failure): configuration, directories, database,
authentication, audit logging, reporting.

Non-critical phases (degrade / continue): forensic parsers, dataset discovery,
knowledge base, IOC database, threat intelligence, ML models, LLM service,
RAG pipeline, evaluation, background workers.

## Phase Summary

| Phase | Initialiser | Critical | Success | Degraded / Failed behaviour |
|-------|-------------|----------|---------|-----------------------------|
| configuration | `ConfigurationValidator` | yes | Valid YAML + env | Abort — actionable validation errors |
| directories | `DirectoryManager` | yes | Required tree writable | Abort — path/permission errors |
| database | `DatabaseInitializer` | yes | Connectivity, schema, roles | Abort — connection/migration error |
| authentication | `AuthInitializer` | yes | JWT, hasher, role users | Abort — missing users/roles |
| audit_logging | `AuditInitializer` | yes | Audit sink ready | Abort |
| forensic_parsers | `ParserInitializer` | no | Libraries available | `DEGRADED` — list unavailable parsers |
| dataset_discovery | `DatasetInitializer` | no | Scan complete (0 OK) | `DEGRADED` on scan exception |
| knowledge_base | `KnowledgeInitializer` | no | Chroma / embeddings | `DEGRADED` without chromadb |
| ioc_database | `KnowledgeInitializer` | no | IOC store ready | `DEGRADED` on load failure |
| threat_intelligence | `ThreatIntelInitializer` | no | YARA/Sigma/MITRE | `DEGRADED` when rules missing |
| ml_models | `AIInitializer` | no | Trained models listed | `DEGRADED` when none trained |
| llm_service | `AIInitializer` | no | Ollama healthy | `DEGRADED` — rule fallback |
| rag_pipeline | `AIInitializer` | no | Retriever ready | `DEGRADED` — plain LLM prompts |
| reporting | `ReportingInitializer` | yes | Output paths ready | Abort |
| evaluation | `EvaluationInitializer` | no | Ground truth loaders | `DEGRADED` when datasets missing |
| background_workers | `WorkerInitializer` | no | Tasks registered | Continue; tasks may no-op |

## Failure Modes

1. **Critical failure** — sequencer stops immediately; `system_status=unavailable`;
   `critical_failures` lists phase + message; later phases do not run.
2. **Non-critical degradation** — full sequence completes;
   `system_status=degraded`; `degraded_services` lists phases/capabilities.
3. **Unexpected exception** — captured as phase `FAILED` with exception text;
   treated as degraded for non-critical phases.

## Degradation Behaviour

- **No Ollama:** LLM phase degraded; `RuleBasedAnalyzer` remains available;
  `RecoveryManager` marks ollama fallback active.
- **No pytsk3 / volatility3:** parser phase degraded; available parsers remain
  listed in phase details.
- **Empty datasets:** discovery completes with `total_discovered=0` — valid.
- **No knowledge / ML:** RAG and ML scoring disabled; rule triage and reporting
  continue (see Prompt 12.14 integration tests).

## Recovery Procedures

| Symptom | Runtime response | Operator action |
|---------|------------------|-----------------|
| Ollama returns | `ServiceMonitor` probe healthy; next triage can use LLM | Ensure model pulled; confirm `DFAT_AI_ENGINE__LLM_API_URL` |
| Vector store errors | `RecoveryManager` re-inits knowledge base | Check chromadb path permissions |
| Database blips | Retry with backoff | Verify DB URL / server |
| New dataset files | `DatasetWatcher` registers on interval | Confirm `data/datasets/` writable |

Graceful shutdown (`ShutdownHandler`) stops background tasks, waits for pipeline
jobs, flushes audit buffers, and disposes the DB engine.

## Verification

```bash
make verify-system-init   # boots isolated env, checks phases/capabilities
make test-prompt12        # unit + integration + frontend Prompt 12 suite
make test-boot            # boot scenario integration tests
```

See also: ADR-029, ADR-030, ADR-031; `docs/operations/TROUBLESHOOTING.md`.
