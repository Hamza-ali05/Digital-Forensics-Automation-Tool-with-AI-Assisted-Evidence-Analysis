# ADR-025: RAG-Augmented AI Analysis

## Status
Accepted

## Context
Prompt 11 extends DFAT with a local knowledge base (vector store, IOC database,
knowledge graph). Investigative AI summaries benefit from prior-case context, but
must remain grounded in retrieved evidence rather than model parametric memory.

## Decision
Introduce `RAGEnhancedAnalyzer` alongside the existing `LocalLLMClient`. When
`ai_engine.use_rag` is enabled, triage injects retrieved context via
`RAGContextBuilder` and versioned `RAGPromptTemplates`. Empty knowledge-base
results fall back to standard local LLM prompts; LLM unavailability falls back
to `RuleBasedAnalyzer`.

## Consequences
- RAG is opt-in and additive — non-RAG analysis paths remain unchanged.
- Audit events record `rag_used`, contributing datasets, and prompt version.
- `classification_reasoning` is annotated with `[rag_sources: ...]` for traceability.
- Related: ADR-017, ADR-026.
