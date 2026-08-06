# ADR-004: Repository Pattern with File-Based Storage

## Status
Accepted

## Context
SQLite or PostgreSQL would be premature for an MSc prototype. Persistence must remain simple, testable, and portable.

## Decision
Use the repository pattern with file-based JSON storage (`LocalFileStorage` / `SecureStorage`). Domain ports (`IEvidenceRepository`, etc.) abstract persistence so a later DB backend can replace files without changing engines.

## Consequences
- Evidence, artefacts, and reports persist as JSON under configured data directories.
- Unit/integration tests can isolate storage via temporary directories.
- Migration to a relational store is possible behind the same interfaces.
