# ADR-001: Design Science Research Methodology

## Status
Accepted

## Context
DFAT is an MSc Cybersecurity research artefact. Architectural choices must support a design–build–evaluate cycle rather than production-scale operations.

## Decision
Treat the system as a Design Science Research (DSR) artefact (Hevner et al., 2004). Architecture decisions prioritise evaluability, reproducibility, and scholarly contribution over horizontal scaling or enterprise ops concerns.

## Consequences
- Prefer clear stage boundaries and measurable outputs (hashes, metrics, dual reports).
- Accept prototype trade-offs (file storage, local single-node LLM).
- Evaluation (benchmarks, usability questionnaire) is a first-class pipeline stage.
