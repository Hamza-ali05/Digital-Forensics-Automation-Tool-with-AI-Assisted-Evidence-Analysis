# ADR-028: Dataset Auto-Discovery

## Status
Accepted

## Context
Forensic benchmark, threat-intel, and ML training files arrive in heterogeneous
formats across nested directories. Manual registration does not scale and risks
stale metadata during dissertation evaluation runs.

## Decision
`DatasetScanner` recursively discovers files under `dataset_intelligence.datasets_dir`,
skipping hidden paths and oversize files. `DatasetRegistry` orchestrates classify →
validate → preprocess → persist, with optional startup scan and filesystem watcher.
Duplicate content is detected by SHA-256 hash and timestamp-updated rather than
re-ingested.

## Consequences
- Admin API `POST /api/v1/datasets/scan` triggers on-demand discovery.
- `/statistics` aggregates category, format, status, and total indexed size.
- Soft-delete removes registry entries without deleting source files.
- Related: `DATASET_INTELLIGENCE.md`.
