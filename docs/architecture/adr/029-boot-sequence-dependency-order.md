# ADR-029: Boot Sequence Dependency Order

## Status
Accepted

## Context
DFAT must initialise configuration, storage, database, authentication, forensic
parsers, knowledge, AI, threat intelligence, reporting, evaluation, and background
workers before accepting API traffic. Earlier Prompt 12 phases introduced
per-subsystem initialisers; without a single ordered orchestrator, startup races
and partial readiness were hard to diagnose.

## Decision
`BootSequencer` runs a fixed 16-phase sequence. Critical phases
(configuration, directories, database, authentication, audit logging, reporting)
abort startup with `SystemReadiness.UNAVAILABLE` on failure. Non-critical phases
(parsers, datasets, knowledge, threat intel, ML, LLM, RAG, evaluation, workers)
record `DEGRADED` / `FAILED` and allow the process to continue.

## Consequences
- Operators receive a single `StartupReport` with per-phase status and timings.
- Frontend `StartupScreen` / `/system/startup` expose the same report.
- Recovery and health monitoring build on the same readiness model (ADR-030).
- Related: ADR-030, ADR-031; `docs/architecture/SYSTEM_INITIALIZATION.md`.
