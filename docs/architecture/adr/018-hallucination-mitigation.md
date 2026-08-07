# ADR-018: Hallucination Mitigation for Local LLM Outputs

## Status
Accepted

## Context
Base LLaMA-3 (not domain-fine-tuned ForensicLLM; Sharma et al., 2025) can
fabricate artefact IDs, categories, suspicion levels, and overconfident claims.
Investigative narratives must remain advisory; structured JSON is authoritative
(Scanlon et al., 2023).

## Decision
Every LLM response that feeds investigator-facing output passes through
`HallucinationGuard` and/or `AIResponseValidator`:

1. **ID checks** — discard/flag artefact IDs absent from the input set.
2. **Taxonomy checks** — flag fabricated categories and suspicion levels.
3. **Assertion checks** — flag unsupported certainty language.
4. **Knowledge checks** — flag IPs/domains/hashes absent from known facts.
5. **Risk levels** — `low` / `medium` / `high` drive monitoring and UI caution.
6. **Clean response** — annotate hallucinated IDs as `[HALLUCINATED_ID:…]`.

Classification parsers discard hallucinated IDs; Q&A and explanations always
attach a `HallucinationReport`.

## Consequences
- False-positive flags may reduce narrative fluency; prefer safety.
- Audit/monitor logs record risk metadata without prompt/evidence bodies.
- Dual-output JSON remains the evidential record regardless of narrative quality.
