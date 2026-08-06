# ADR-003: Dual-Output Report Format

## Status
Accepted

## Context
LLM narrative generation is non-deterministic. Forensic outputs require a reproducible, auditable evidential record.

## Decision
Produce dual-output reports:
1. **Structured JSON** — authoritative, schema-validated, integrity-hashed evidential layer.
2. **LLM / rule-based narrative** — supplementary investigative summary only.

## Consequences
- JSON integrity hashes cover the artefacts array (not volatile report metadata).
- Narrative templates include an explicit advisory disclaimer.
- Consumers and evaluators treat JSON as the source of truth for artefact claims.
