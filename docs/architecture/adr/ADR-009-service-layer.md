# ADR-009: Service Layer Pattern

## Status
Accepted

## Context
Embedding business logic in FastAPI route handlers couples forensic workflows to HTTP and hinders unit testing.

## Decision
Place application/business logic in a `services/` layer. API routes remain thin: validate input, call a service, format the response.

## Consequences
- Services orchestrate repositories, pipeline components, and audit logging.
- Pipeline logic stays testable without `TestClient`.
- Route modules (`auth`, `users`, `health`, existing forensic routes) depend on services via DI, not on ORM/session details directly.
