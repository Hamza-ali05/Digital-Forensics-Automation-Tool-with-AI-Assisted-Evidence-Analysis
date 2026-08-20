# Knowledge Management Architecture

## Overview

The knowledge layer provides unified retrieval across vector embeddings, structured
IOC records, and a forensic knowledge graph. It powers RAG context injection and
investigator query APIs.

## Components

| Component | Storage | Purpose |
|-----------|---------|---------|
| `LocalEmbeddingEngine` | In-memory model | 384-dim local embeddings |
| `ForensicVectorStore` | ChromaDB | Similarity search collections |
| `IOCKnowledgeBase` | SQLite | Structured IOC lookup/search |
| `ForensicKnowledgeGraph` | JSON persist | Entity relationships |
| `UnifiedRetriever` | — | Merged ranked retrieval |
| `DocumentIndexer` | — | Dataset → vector indexing |
| `RAGContextBuilder` | — | Prompt-ready context blocks |

## Vector Collections

- `artefacts` — pipeline artefact embeddings
- `knowledge` — documentation and general forensic text
- `iocs` — indicator-oriented content
- `threat_intel` — feed and rule-derived text
- `benchmark` — evaluation ground-truth snippets

## API Surface

- `GET /api/v1/knowledge/stats`
- `POST /api/v1/knowledge/query`
- `GET /api/v1/knowledge/graph/stats`
- `GET /api/v1/knowledge/iocs`
- `GET /api/v1/knowledge/iocs/stats`

## RAG Integration

When enabled, `RAGEnhancedAnalyzer` queries the retriever before LLM classification
and summary. Empty retrieval falls back to standard prompts (see ADR-025).

## Related ADRs

- [ADR-025](adr/025-rag-augmented-ai.md)
- [ADR-026](adr/026-local-embeddings-only.md)
