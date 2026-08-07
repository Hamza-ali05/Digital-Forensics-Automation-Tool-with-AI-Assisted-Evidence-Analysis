# ADR-009: Service Layer Pattern

## Status
Accepted

## Context
API route handlers should not contain business logic. Testability requires
business logic to be invokable without HTTP or a running API server.

## Decision
All business logic lives in service classes under `services/`:

- **Services:** `UserService`, `EvidenceService`, `AnalysisService`,
  `ReportService`, `EvaluationService`, `AuditService`.
- **Injection:** Services receive repositories and infrastructure via constructor
  injection (`ServicesContainer` in `container.py`).
- **Contracts:** Services accept and return Pydantic domain models, never ORM objects.
- **Routes:** Thin — validate HTTP input, extract authenticated user via
  `Depends`, call one service method, format the response.

## Consequences
- Services are independently testable with mocked repositories (see
  `tests/unit/services/`).
- Dual logging (database `audit_repo` + file-based `ForensicAuditLogger`) for
  forensic compliance is coordinated in `AuditService`, not in routes.
- Pipeline orchestration remains sync; async services delegate via
  `asyncio.to_thread` where needed.
- Route modules depend on services via DI, not on SQLAlchemy session details.
