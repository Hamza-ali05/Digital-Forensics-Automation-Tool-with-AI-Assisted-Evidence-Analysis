# ADR-007: SQLAlchemy Async Persistence

## Status
Accepted

## Context
ADR-004 established file-based repositories with the note that "the repository
interface allows future migration." As the system grows to support multi-user
access, audit persistence, and evaluation history, structured persistence
becomes necessary.

## Decision
Adopt SQLAlchemy 2.0 async with SQLite for development and PostgreSQL as a
production option. ORM models are separate from Pydantic domain models. The
`IRepository` interface from Prompt 1 / Prompt 3 remains the contract — only
the implementations change. Alembic manages schema versioning; migration files
are immutable once committed.

Evidence **files** are never stored in the database — only metadata and
integrity hashes.

## Consequences
- Repository implementations must convert between ORM and domain models using
  mappers.
- Database sessions must be properly managed via the DI container.
- Migration discipline is required: schema changes use new migration files,
  never edits to committed revisions.
- Default role IDs (`role-admin`, `role-investigator`, `role-analyst`,
  `role-viewer`) are stable constants for the auth system.
