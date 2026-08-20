# ADR-026: Local Embeddings Only

## Status
Accepted

## Context
Cloud embedding APIs would transmit forensic artefact text and dataset content
outside the investigator environment, violating the local-only constraint
established in ADR-017 for LLM inference.

## Decision
All vector embeddings are generated locally via `sentence-transformers`
(`all-MiniLM-L6-v2`, 384 dimensions) through `LocalEmbeddingEngine`. ChromaDB
persists vectors on disk under configurable dataset-intelligence paths. No
remote embedding or vector-database SaaS is used.

## Consequences
- Optional dependency group `dfat[intelligence]` installs embedding/Chroma stack.
- Embedding model is lazy-loaded on first use to reduce startup cost.
- Artefact and document serialization reuse existing forensic serializers.
- Related: ADR-017, ADR-025.
