# ADR-006: Rule-Based Fallback Analyzer

## Status
Accepted

## Context
Local LLM integration may fail (runtime unavailable, schedule risk, or response errors). Triage must still produce ranked artefacts for the pipeline.

## Decision
Provide a `RuleBasedAnalyzer` implementing the same `IArtefactAnalyzer` port. When the LLM is unavailable or `use_fallback` / `enable_fallback` is set, select the rule-based analyser.

## Consequences
- Functional (heuristic) triage always available.
- Pipeline and API can force fallback for reproducible offline runs.
- Narrative quality is lower than LLM mode; JSON evidential layer remains authoritative (ADR-003).
