# Dataset Intelligence Architecture

## Overview

The dataset intelligence subsystem discovers, classifies, validates, preprocesses,
and registers local forensic datasets used by knowledge indexing, ML training,
and threat-intel ingestion.

## Components

| Component | Responsibility |
|-----------|----------------|
| `DatasetScanner` | Recursive filesystem discovery, MIME/format detection |
| `DatasetClassifier` | Heuristic category, RQ mapping, supported modules |
| `DatasetValidator` | Integrity and schema checks |
| `DatasetPreprocessor` | Category-aware normalization |
| `DatasetRegistry` | Orchestration and persistence via `DatasetRepository` |
| `DatasetWatcher` | Optional filesystem change notifications |

## Lifecycle

1. **Discover** — scan directory tree, compute SHA-256, capture metadata.
2. **Classify** — assign primary category, tags, research objectives.
3. **Validate** — reject or mark failed datasets.
4. **Preprocess** — enrich records and mark ready for downstream modules.
5. **Persist** — store in SQLite via Alembic migration `007_dataset_intelligence`.
6. **Index** — `DocumentIndexer` writes embeddings to vector collections.

## API Surface

- `GET /api/v1/datasets` — list/filter registry records
- `GET /api/v1/datasets/statistics` — aggregate stats
- `POST /api/v1/datasets/scan` — admin discovery
- `POST /api/v1/datasets/{id}/reindex` — vector re-index
- `POST /api/v1/datasets/{id}/refresh` — re-validate/reprocess
- `DELETE /api/v1/datasets/{id}` — soft-remove

## Configuration

Settings live under `settings.dataset_intelligence`: `datasets_dir`,
`vector_store_path`, `knowledge_graph_path`, `ioc_database_path`, `scan_on_startup`,
`watch_for_changes`.

## Related ADRs

- [ADR-028](adr/028-dataset-auto-discovery.md)
