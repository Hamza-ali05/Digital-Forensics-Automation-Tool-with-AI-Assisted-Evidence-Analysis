# ADR-002: Local LLM Only — No Cloud Inference

## Status
Accepted

## Context
Chain-of-custody and GDPR constraints prohibit transmitting forensic evidence to external inference APIs (Scanlon et al., 2023).

## Decision
All LLM inference runs locally (LLaMA-3 via Ollama or equivalent). The HTTP client must reject non-localhost endpoints.

## Consequences
- `LocalLLMClient` asserts local hosts only (`127.0.0.1`, `localhost`, `::1`).
- No cloud AI SDKs or remote model hosts in the processing path.
- Investigators must provision a local model runtime; offline fallback remains available (ADR-006).
