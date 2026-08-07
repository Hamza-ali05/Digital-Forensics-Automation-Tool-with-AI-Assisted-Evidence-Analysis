# ADR-020: Rule-Based Triage as Primary Deterministic Baseline

## Status
Accepted

## Context
Local LLM availability is not guaranteed in offline labs or CI. Even when
available, base LLaMA-3 rankings are non-deterministic and may be less accurate
than a domain-fine-tuned ForensicLLM (Sharma et al., 2025). Research runs need a
deterministic, explainable baseline.

## Decision
Rule-based triage (`RuleBasedTriageEngine` / `RuleBasedAnalyzer`) is the
**primary deterministic baseline**. LLM classification and ranking **enhance**
results when healthy but do not replace the rule engine as the offline authority.

Operational rules:

- `TriageStage` always computes rule-based scores (ADR-016).
- Weighted merge prefers rules: `0.4 * llm + 0.6 * rule` when both exist.
- Missing LLM scores or LLM failures fall back to rule-only scores.
- API `use_fallback: true` forces the rule-based analyser for reproducibility.
- `RuleBasedAnalyzer.is_available()` is always `True`.

## Consequences
- CI and offline evaluations produce stable rankings without Ollama.
- Narrative quality is lower in rule-only mode; JSON remains authoritative
  (ADR-003).
- Related: ADR-006, ADR-016.
