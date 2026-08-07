# ADR-007: SQLAlchemy Async Persistence

## Status
Accepted

## Context
ADR-004 established file-based repositories with the note that "the repository
interface allows future migration." Multi-user access, evaluation history, and
audit persistence require structured storage beyond JSON files on disk.

## Decision
Adopt SQLAlchemy 2.0 async with SQLite for development and optional
PostgreSQL for production. ORM models are separate from Pydantic domain models.
The `IRepository` interface from Prompt 1 remains unchanged — only
implementations evolve (async SQLAlchemy repos for the API path; file-based
repos retained as fallbacks for the sync pipeline).

Alembic manages schema versioning; committed migration files are immutable.
Evidence **files** are never stored in the database — only metadata, integrity
hashes, users, sessions, and audit records.

## Consequences
- A mapper layer (`database/mappers.py`) converts between ORM and domain models.
- Database sessions are managed via the DI container (`DatabaseContainer`).
- Migration discipline is enforced via Alembic (`001` initial schema, seed roles).
- Stable role IDs (`role-admin`, `role-investigator`, `role-analyst`,
  `role-viewer`) are constants shared with auth and migrations.
