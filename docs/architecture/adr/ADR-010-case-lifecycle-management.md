# ADR-010: Case Lifecycle Management

## Status
Accepted

## Context
Prompt 1 provided `CaseMetadata` as a lightweight evidence association record.
Operational investigations require a full case lifecycle (open → active → review →
close → archive), investigator assignment, and evidence linkage before pipeline
execution. ACPO-aligned handling also needs lead accountability before a case
can be opened.

## Decision
Introduce a `Case` domain model that **wraps** (does not replace) `CaseMetadata`,
with explicit `CaseStatus` transitions enforced by `CASE_STATUS_TRANSITIONS`.
`CaseService` owns lifecycle operations, investigator soft-assignment, and
evidence association. Opening a case requires a lead investigator
(`NoLeadInvestigatorError` otherwise). Closing a case seals custody chains for
all linked evidence.

Persistence uses dedicated `cases` / `case_investigators` tables (migration
`002`) via `SQLAlchemyCaseRepository`. REST routes under `/api/v1/cases` are
thin wrappers with RBAC on the additive `cases` resource.

## Consequences
- Pipeline/acquisition code continues to use `CaseMetadata` unchanged.
- Invalid transitions raise `InvalidCaseTransitionError` (HTTP 409).
- Case APIs are additive; Prompt 2 evidence registration routes remain intact.
