# ADR-022: Report Schema Versioning

## Status
Accepted

## Context
Structured forensic reports must remain readable as the tool evolves. Breaking
field changes without versioning would invalidate stored reports and benchmarks.

## Decision
Reports declare `schema_version` (currently `1.0.0`). The canonical JSON Schema
lives under `dfat.reporting.schema` with a registry of supported versions.
`ReportSchemaValidator` rejects documents with unsupported versions.
Backward-compatible additive changes may keep the same major version; breaking
changes require a new registered version and migration notes.

## Consequences
- Exporters and verifiers share one schema source of truth.
- Older reports remain verifiable while their version stays registered.
- API/OpenAPI consumers can branch on `schema_version`.
