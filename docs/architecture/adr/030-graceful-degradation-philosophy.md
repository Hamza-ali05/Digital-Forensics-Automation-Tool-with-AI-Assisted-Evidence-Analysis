# ADR-030: Graceful Degradation Philosophy

## Status
Accepted

## Context
Dissertation deployments often lack optional dependencies (Ollama, pytsk3,
volatility3, ChromaDB). Hard-failing the entire platform when an optional
subsystem is missing would block case/evidence workflows and rule-based triage
that remain scientifically valid.

## Decision
Treat optional intelligence services as degradable, not fatal:
- Missing Ollama → rule-based LLM fallback (`RuleBasedAnalyzer`).
- Missing forensic libraries → parser phase `DEGRADED`; available parsers listed.
- Empty knowledge / ML → RAG and ML scoring disabled; rule triage continues.
- Runtime `ServiceMonitor` + `RecoveryManager` re-probe services and activate
  fallbacks without crashing the API process.

Critical failures (database, auth, audit, directories, reporting) still abort.

## Consequences
- System status is `READY`, `DEGRADED`, or `UNAVAILABLE` — never silent partial boot.
- UI shows `DegradedBanner` and admin System Status for operator visibility.
- Benchmarks and reports remain valid under rule-based fallback (Prompt 12.14).
- Related: ADR-017, ADR-020, ADR-029.
