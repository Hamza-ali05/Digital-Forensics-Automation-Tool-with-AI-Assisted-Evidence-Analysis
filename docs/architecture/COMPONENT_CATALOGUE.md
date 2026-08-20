# Component Catalogue

This catalogue lists the major DFAT components by architectural layer. It is intended as a practical index for implementation review, dissertation mapping, and future extension work.

## 1. Domain Layer

### Models

| Class / Type | Module | Purpose | Interface / Notes |
|--------------|--------|---------|-------------------|
| `Artefact` | `src/dfat/core/models/artefact.py` | canonical parsed artefact model | base forensic finding |
| `RankedArtefact` | `src/dfat/core/models/artefact.py` | artefact plus triage metadata | extends `Artefact` |
| `ArtefactSet` | `src/dfat/core/models/artefact.py` | grouped artefacts for one evidence item | normalized parser output |
| `CaseMetadata` | `src/dfat/core/models/evidence.py` | case identity and ownership metadata | used across pipeline |
| `EvidenceImage` | `src/dfat/core/models/evidence.py` | loaded evidence representation | disk image / memory dump |
| `JSONReport` | `src/dfat/core/models/report.py` | structured report domain model | evidential layer |
| `NarrativeReport` | `src/dfat/core/models/report.py` | narrative report domain model | advisory layer |
| `BenchmarkResult` | `src/dfat/core/models/evaluation.py` | benchmark metrics result | RQ4 / performance |
| `UsabilityResponse` | `src/dfat/core/models/evaluation.py` | anonymized questionnaire response | RQ5 |

### Interfaces / Ports

| Interface | Module | Purpose |
|-----------|--------|---------|
| `IArtefactParser` | `src/dfat/core/interfaces/parser.py` | parser contract |
| `IReportGenerator` | `src/dfat/core/interfaces/reporter.py` | report-generation contract |
| `IArtefactAnalyzer` | `src/dfat/core/interfaces/analyzer.py` | AI / fallback analysis contract |
| `IEvaluator` | `src/dfat/core/interfaces/evaluator.py` | evaluation contract |
| `IRepository` | `src/dfat/core/interfaces/repository.py` | generic persistence contract |
| `ICaseRepository` | `src/dfat/core/interfaces/case_repository.py` | case-repository contract |

### Enums and Supporting Types

| Enum / Module | Purpose |
|---------------|---------|
| `EvidenceType` in `src/dfat/core/enums.py` | disk vs memory evidence taxonomy |
| `ArtefactCategory` in `src/dfat/core/enums.py` | 7-category artefact taxonomy |
| `PipelineStage` in `src/dfat/core/enums.py` | five-stage workflow taxonomy |
| `SuspicionLevel` in `src/dfat/core/enums.py` | triage severity |
| `ReportFormat` in `src/dfat/core/enums.py` | report-output formats |
| `HashAlgorithm` in `src/dfat/core/enums.py` | integrity algorithm selection |

## 2. Forensic Engine

### Acquisition and Orchestration

| Class | Module | Purpose | Interface / Notes |
|------|--------|---------|-------------------|
| `ForensicOrchestrator` | `src/dfat/forensic_engine/orchestrator.py` | routes evidence through parsers | central parsing coordinator |
| `DiskImageHandler` | `src/dfat/forensic_engine/acquisition/image_handler.py` | disk-image acquisition | stage 1 |
| `MemoryDumpHandler` | `src/dfat/forensic_engine/acquisition/memory_handler.py` | memory-dump acquisition | stage 1 |
| `IntegrityChecker` | `src/dfat/forensic_engine/acquisition/integrity.py` | hash verification | chain-of-custody support |
| `ArtefactNormalizer` | `src/dfat/forensic_engine/normalizer.py` | merges parser outputs | normalized `ArtefactSet` |

### Parsers

| Parser | Module | Categories | Evidence Types |
|--------|--------|------------|----------------|
| `FileSystemParser` | `src/dfat/forensic_engine/parsers/filesystem.py` | filesystem metadata | disk image |
| `RegistryParser` | `src/dfat/forensic_engine/parsers/registry.py` | registry keys | disk image |
| `BrowserHistoryParser` | `src/dfat/forensic_engine/parsers/browser.py` | browser history | disk image |
| `EventLogParser` | `src/dfat/forensic_engine/parsers/eventlog.py` | event log | disk image |
| `ProcessListParser` | `src/dfat/forensic_engine/parsers/memory/process.py` | running processes | memory dump |
| `NetworkArtefactParser` | `src/dfat/forensic_engine/parsers/memory/network.py` | network connections | memory dump |
| `CodeInjectionParser` | `src/dfat/forensic_engine/parsers/memory/injection.py` | injected code | memory dump |
| `MemoryRegistryParser` | `src/dfat/forensic_engine/parsers/memory/registry_mem.py` | registry keys | memory dump |

### Processing and Triage

| Class | Module | Purpose |
|------|--------|---------|
| `ArtefactCategoriser` | `src/dfat/forensic_engine/processing/categoriser.py` | post-parse category support |
| `ArtefactCorrelator` | `src/dfat/forensic_engine/processing/correlator.py` | relate artefacts |
| `ArtefactDeduplicator` | `src/dfat/forensic_engine/processing/deduplicator.py` | remove duplicates |
| `IOCDetector` | `src/dfat/forensic_engine/processing/ioc_detector.py` | detect indicators of compromise |
| `RelationshipMapper` | `src/dfat/forensic_engine/processing/relationship_mapper.py` | map artefact relationships |
| `TimelineGenerator` | `src/dfat/forensic_engine/processing/timeline.py` | create chronology |
| `ArtefactStandardiser` | `src/dfat/forensic_engine/processing/standardiser.py` | normalize processing fields |
| `RuleBasedTriageEngine` | `src/dfat/forensic_engine/triage/rule_engine.py` | deterministic triage |
| `ScoringEngine` | `src/dfat/forensic_engine/triage/scoring.py` | suspicion scoring |
| `TriageAggregator` | `src/dfat/forensic_engine/triage/aggregator.py` | summary statistics aggregation |

## 3. AI Engine

| Class / Component | Module | Purpose | Interface / Notes |
|------------------|--------|---------|-------------------|
| `LocalLLMClient` | `src/dfat/ai_engine/analyzer.py` | unified AI analysis client | local Ollama path |
| `LLMConfig` | `src/dfat/ai_engine/llm/config.py` | model and endpoint config | prompt version anchor |
| `LLMConnectionManager` | `src/dfat/ai_engine/llm/connection.py` | local-only health and transport | rejects external URLs |
| `OllamaClient` | `src/dfat/ai_engine/llm/client.py` | HTTP communication with Ollama | model invocation |
| `ForensicPromptTemplates` | `src/dfat/ai_engine/llm/prompts.py` | versioned prompt catalogue | reproducibility support |
| `LLMArtefactClassifier` | `src/dfat/ai_engine/classification/classifier.py` | classify artefacts | AI triage |
| `LLMRelevanceRanker` | `src/dfat/ai_engine/ranking/ranker.py` | rank relevance | AI triage |
| `LLMInvestigativeSummarizer` | `src/dfat/ai_engine/summarization/summarizer.py` | summary generation | AI narrative support |
| `ClassificationResponseParser` | `src/dfat/ai_engine/classification/parser.py` | parse classifier output | JSON contract |
| `RankingResponseParser` | `src/dfat/ai_engine/ranking/parser.py` | parse ranking output | JSON contract |
| `SummaryResponseValidator` | `src/dfat/ai_engine/summarization/validator.py` | validate summary structure | response safety |
| `HallucinationGuard` | `src/dfat/ai_engine/validation/hallucination_guard.py` | detect fabricated claims | risk mitigation |
| `AIResponseValidator` | `src/dfat/ai_engine/validation/response_validator.py` | response safety pipeline | guard integration |
| `AIResponseCache` | `src/dfat/ai_engine/caching/response_cache.py` | response caching | reproducibility / performance |
| `RuleBasedAnalyzer` | `src/dfat/ai_engine/fallback/rule_based.py` | deterministic fallback | `IArtefactAnalyzer` |
| `AIMonitor` | `src/dfat/ai_engine/monitoring/ai_monitor.py` | AI metrics / audit integration | observability |

## 4. Reporting Layer

| Class | Module | Purpose | Interface / Notes |
|------|--------|---------|-------------------|
| `StructuredJSONExporter` | `src/dfat/reporting/json_layer.py` | primary evidential record | deterministic JSON |
| `NarrativeAssembler` | `src/dfat/reporting/narrative.py` | narrative assembly | disclaimer-wrapped |
| `DualOutputReportBuilder` | `src/dfat/reporting/report_builder.py` | combine JSON + narrative | `IReportGenerator` |
| `ReportSchemaValidator` | `src/dfat/reporting/schema.py` | schema validation | versioned report schema |
| `ReportIntegrityVerifier` | `src/dfat/reporting/integrity.py` | report tamper verification | integrity support |
| `ReproducibilityVerifier` | `src/dfat/reporting/reproducibility.py` | compare report runs | reproducibility proof |
| `PDFReportExporter` | `src/dfat/reporting/exporters/pdf_exporter.py` | PDF export | downstream delivery |
| `HTMLReportExporter` | `src/dfat/reporting/exporters/html_exporter.py` | HTML export | downstream delivery |
| `JSONFileExporter` | `src/dfat/reporting/exporters/json_file_exporter.py` | JSON file export | downstream delivery |
| `AuditReportGenerator` | `src/dfat/reporting/generators/audit_report.py` | audit-trail report | admin / forensic review |
| `CustodyReportGenerator` | `src/dfat/reporting/generators/custody_report.py` | custody report | evidence accountability |

## 5. Evaluation Layer

| Class | Module | Purpose |
|------|--------|---------|
| `GroundTruthLoader` | `src/dfat/evaluation/benchmark/ground_truth.py` | benchmark dataset facade |
| `DFRWSHandler` | `src/dfat/evaluation/benchmark/dfrws_handler.py` | DFRWS dataset support |
| `CFReDSHandler` | `src/dfat/evaluation/benchmark/cfreds_handler.py` | CFReDS dataset support |
| `MetricsCalculator` | `src/dfat/evaluation/benchmark/metrics.py` | precision / recall / F1 / TTT |
| `BenchmarkComparator` | `src/dfat/evaluation/benchmark/comparator.py` | TP/FP/FN comparison |
| `PerformanceAnalyzer` | `src/dfat/evaluation/benchmark/performance.py` | mean / median / p95 analysis |
| `MetricsVisualiser` | `src/dfat/evaluation/benchmark/visualisation.py` | benchmark visualization support |
| `QuestionnaireInstrument` | `src/dfat/evaluation/usability/questionnaire.py` | ethics-locked instrument |
| `ResponseCollector` | `src/dfat/evaluation/usability/response_collector.py` | anonymized collection |
| `ResponseAnalyzer` | `src/dfat/evaluation/usability/response_analyzer.py` | descriptive statistics + CI |
| `TobinComparison` | `src/dfat/evaluation/usability/tobin_comparison.py` | literature benchmark comparison |

## 6. Infrastructure Layer

### Persistence and Repositories

| Class | Module | Purpose |
|------|--------|---------|
| `DatabaseEngine` | `src/dfat/database/engine.py` | async DB engine and sessions |
| `SQLAlchemyUserRepository` | `src/dfat/database/repositories/user_repo.py` | user persistence |
| `SQLAlchemyCaseRepository` | `src/dfat/database/repositories/case_repo.py` | case persistence |
| `SQLAlchemyEvidenceRepository` | `src/dfat/database/repositories/evidence_repo.py` | evidence metadata persistence |
| `SQLAlchemyArtefactRepository` | `src/dfat/database/repositories/artefact_repo.py` | artefact persistence |
| `SQLAlchemyReportRepository` | `src/dfat/database/repositories/report_repo.py` | report persistence |
| `SQLAlchemyPipelineRepository` | `src/dfat/database/repositories/pipeline_repo.py` | pipeline job persistence |
| `SQLAlchemyAuditRepository` | `src/dfat/database/repositories/audit_repo.py` | audit persistence |
| `SQLAlchemyBenchmarkRepository` | `src/dfat/database/repositories/evaluation_repo.py` | benchmark persistence |
| `SQLAlchemyUsabilityRepository` | `src/dfat/database/repositories/evaluation_repo.py` | questionnaire persistence |
| `SessionRepository` | `src/dfat/database/repositories/session_repo.py` | auth-session persistence |

### Storage and Logging

| Class | Module | Purpose |
|------|--------|---------|
| `LocalFileStorage` | `src/dfat/infrastructure/storage/local_storage.py` | evidence file storage |
| `SecureStorage` | `src/dfat/infrastructure/storage/secure_storage.py` | report storage |
| `FileSystemEvidenceRepository` | `src/dfat/infrastructure/repositories/evidence_repo.py` | file-based evidence adapter |
| `JSONArtefactRepository` | `src/dfat/infrastructure/repositories/artefact_repo.py` | file-based artefact adapter |
| `FileSystemReportRepository` | `src/dfat/infrastructure/repositories/report_repo.py` | file-based report adapter |
| `ForensicAuditLogger` | `src/dfat/infrastructure/logging/audit_logger.py` | append-only forensic audit log |

## 7. Application Layer

### Services

| Class | Module | Purpose |
|------|--------|---------|
| `UserService` | `src/dfat/services/user_service.py` | authentication and user operations |
| `CaseService` | `src/dfat/services/case_service.py` | case lifecycle and investigator management |
| `EvidenceService` | `src/dfat/services/evidence_service.py` | evidence metadata operations |
| `EvidenceManagementService` | `src/dfat/services/evidence_management_service.py` | validation, custody, status workflows |
| `AnalysisService` | `src/dfat/services/analysis_service.py` | analysis workflow entrypoints |
| `ReportService` | `src/dfat/services/report_service.py` | report retrieval and export |
| `EvaluationService` | `src/dfat/services/evaluation_service.py` | benchmark and usability operations |
| `AuditService` | `src/dfat/services/audit_service.py` | dual-write audit actions |

### Pipeline Coordination

| Class | Module | Purpose |
|------|--------|---------|
| `PipelineOrchestrator` | `src/dfat/pipeline/orchestrator.py` | overall workflow coordination |
| `JobManager` | `src/dfat/pipeline/job_manager.py` | job state and concurrency |
| `JobRunner` | `src/dfat/pipeline/job_runner.py` | stage execution runtime |
| `ProgressTracker` | `src/dfat/pipeline/progress_tracker.py` | progress updates |
| `PipelineLogger` | `src/dfat/pipeline/pipeline_logger.py` | pipeline event logging |
| `PipelineErrorHandler` | `src/dfat/pipeline/error_handler.py` | stage-level recovery |
| `StageRegistry` | `src/dfat/pipeline/stage_registry.py` | stage registration |
| `AcquisitionStage` | `src/dfat/pipeline/stages/acquisition_stage.py` | stage 1 |
| `ParsingStage` | `src/dfat/pipeline/stages/parsing_stage.py` | stage 2 |
| `TriageStage` | `src/dfat/pipeline/stages/triage_stage.py` | stage 3 |
| `ReportingStage` | `src/dfat/pipeline/stages/reporting_stage.py` | stage 4 |
| `EvaluationStage` | `src/dfat/pipeline/stages/evaluation_stage.py` | stage 5 |

## 8. Presentation Layer

### API Routes

| Route Group | Module | Purpose |
|-------------|--------|---------|
| Auth | `src/dfat/api/routes/auth.py` | login, refresh, logout, password change |
| Users | `src/dfat/api/routes/users.py` | profile and admin user operations |
| Health | `src/dfat/api/routes/health.py` | liveness, readiness, diagnostics |
| Cases | `src/dfat/api/routes/cases.py` | case workflow |
| Evidence | `src/dfat/api/routes/evidence.py` | legacy evidence endpoints |
| Evidence Management | `src/dfat/api/routes/evidence_management.py` | registration, validation, custody, status |
| Analysis | `src/dfat/api/routes/analysis.py` | analysis workflow |
| AI | `src/dfat/api/routes/ai.py` | AI classification, summary, explanation, Q&A |
| Pipeline | `src/dfat/api/routes/pipeline.py` | job submission and progress |
| Reports | `src/dfat/api/routes/reports.py` | retrieval, export, integrity, comparison |
| Evaluation | `src/dfat/api/routes/evaluation.py` | benchmarks and questionnaire |
| Monitoring | `src/dfat/api/routes/monitoring.py` | uptime, metrics, logs |

### Middleware

| Middleware | Module | Purpose |
|------------|--------|---------|
| `RequestIDMiddleware` | `src/dfat/api/middleware/request_id.py` | correlation IDs |
| `CompressionMiddleware` | `src/dfat/api/middleware/compression.py` | response compression |
| `SecurityHeadersMiddleware` | `src/dfat/api/middleware/security_headers.py` | HTTP security headers |
| `RateLimiterMiddleware` | `src/dfat/api/middleware/rate_limiter.py` | request throttling |
| `ResponseCacheMiddleware` | `src/dfat/api/middleware/cache.py` | response caching |
| `AuditTrailMiddleware` | `src/dfat/api/middleware/audit.py` | audit capture |
| `RequestValidationMiddleware` | `src/dfat/api/middleware/validation.py` | request validation |
| `GlobalExceptionHandler` | `src/dfat/api/middleware/error_handler.py` | error normalization |

### Frontend Pages

| Area | Example Pages |
|------|---------------|
| Dashboard | `Dashboard.js`, `dashboard/Dashboard.js` |
| Cases | `cases/CaseList.js`, `cases/CaseCreate.js`, `cases/CaseDetail.js` |
| Evidence | `evidence/EvidenceRegister.js`, `evidence/EvidenceInventory.js`, `evidence/EvidenceDetail.js`, `evidence/IntegrityCheck.js` |
| Pipeline | `pipeline/PipelineRun.js`, `pipeline/PipelineJobs.js`, `pipeline/PipelineDetail.js` |
| Artefacts | `artefacts/ArtefactExplorer.js`, `artefacts/TimelinePage.js`, `artefacts/IOCDashboard.js` |
| AI | `ai/AIAnalysis.js`, `ai/AISummaryViewer.js` |
| Reports | `reports/ReportList.js`, `reports/ReportDetail.js`, `reports/JSONViewer.js` |
| Evaluation | `evaluation/BenchmarkRun.js`, `evaluation/BenchmarkResults.js`, `evaluation/PerformanceDashboard.js`, `evaluation/UsabilityResults.js` |
| Questionnaire | `questionnaire/Questionnaire.js`, `evaluation/Questionnaire.js` |
| Admin / Settings | `admin/UserManagement.js`, `admin/AuditLogs.js`, `admin/Settings.js`, `settings/Settings.js` |

## 9. Architectural Use

This document complements:
- `docs/architecture/ARCHITECTURE.md` for system-level design
- `docs/dissertation/METHODOLOGY_MAPPING.md` for dissertation chapter mapping
- `docs/FUTURE_ENHANCEMENTS.md` for extension planning

Together, these provide a full architectural, research, and operational view of the DFAT system.
