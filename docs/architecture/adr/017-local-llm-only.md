# ADR-017: Local LLM Only (Prompt 5 refinement)

## Status
Accepted

## Context
DFAT processes chain-of-custody evidence. Transmitting artefact content or
prompts to cloud inference APIs would violate GDPR and forensic integrity
constraints (Scanlon et al., 2023). ADR-002 established the principle; Prompt 5
implements enforcement in `LLMConnectionManager` and `OllamaClient`.

## Decision
All AI inference for DFAT runs exclusively on a local Ollama endpoint
(`localhost` / `127.0.0.1` / `0.0.0.0` / `::1`). Non-local URLs raise at
construction time. No cloud AI SDKs are permitted on the triage path.

## Consequences
- `LLMConnectionManager._is_local_url` rejects external hosts.
- Health checks and generate/chat calls target only the local base URL.
- Investigators must provision LLaMA-3 (or compatible) locally.
- Complements ADR-006 / ADR-016 when the local runtime is unavailable.
- Related: ADR-002.
