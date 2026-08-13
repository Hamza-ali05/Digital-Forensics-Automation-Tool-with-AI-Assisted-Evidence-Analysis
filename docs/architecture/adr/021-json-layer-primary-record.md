# ADR-021: JSON Layer as Primary Evidential Record

## Status
Accepted

## Context
Dual-output reporting produces machine-readable JSON and human-readable narrative.
Courts and peer reviewers need a clear primary evidential record that can be
hashed, schema-validated, and reproduced independently of LLM wording.

## Decision
The structured JSON report (`JSONReport` / schema `1.0.0`) is the **primary
evidential record**. The narrative is advisory interpretive text and must always
carry a Scanlon et al. (2023) disclaimer. Integrity hashes cover the canonical
artefact array only, never narrative text or report envelope metadata.

## Consequences
- Integrity and reproducibility checks operate on JSON artefact payloads.
- Narrative changes do not invalidate forensic integrity hashes.
- Export formats (PDF/HTML) must embed or link the JSON layer and disclaimer.
