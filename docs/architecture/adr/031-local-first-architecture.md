# ADR-031: Local-First Architecture

## Status
Accepted

## Context
DFAT is designed for air-gapped and controlled forensic labs. Cloud LLM APIs,
remote embedding services, and unmanaged external threat feeds would violate
evidentiary isolation and the dissertation’s local-LLM constraints (ADR-017,
ADR-026).

## Decision
All Prompt 12 bootstrap and runtime monitoring assume local infrastructure:
- SQLite / local PostgreSQL for metadata.
- Local Ollama for LLM (localhost-only URL validation).
- Local ChromaDB / sentence-transformers for embeddings.
- Local YARA/Sigma rule directories and embedded MITRE catalogue.
- Configuration validator rejects external LLM URLs and production JWT placeholders.

## Consequences
- Startup and health checks probe local services only.
- Operators install optional packages on the same host (`pytsk3`, `volatility3`,
  Ollama models, `chromadb`).
- Troubleshooting focuses on local process/package availability
  (`docs/operations/TROUBLESHOOTING.md`).
- Related: ADR-017, ADR-026, ADR-029, ADR-030.
