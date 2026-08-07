# ADR-016: Rule-Based Triage First

## Status
Accepted

## Context
Local LLM inference may be unavailable, slow, or non-deterministic. Research and
operational runs still require ranked, explainable triage. The risk-management
fallback strategy requires a deterministic baseline that stands alone if the LLM
fails (see also ADR-006).

## Decision
The rule-based triage engine runs **before** LLM triage. This ensures a
deterministic, reproducible baseline is always available. LLM triage **enhances
but does not replace** the rule-based results. If the LLM fails, the rule-based
results stand alone.

Implementation notes:

- `TriageStage` always produces rule-based ranked artefacts via
  `RuleBasedTriageEngine` (scoring, rules, IOC paths).
- When `use_fallback_analyzer` is set, the LLM is unavailable, or LLM triage
  raises, rule-based results remain the authoritative ranking.
- Pipeline API `use_fallback: true` forces the non-LLM path for reproducible runs.

## Consequences
- Offline and CI environments produce deterministic triage without Ollama/LLaMA.
- `triage_source` metadata records rule-based vs LLM-assisted output.
- Complements ADR-002 (local LLM only) and ADR-006 (fallback analyser).
- Narrative quality may be lower in rule-only mode; dual-output JSON remains
  authoritative (ADR-003).
