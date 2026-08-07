# ADR-012: Chain-of-Custody Immutability

## Status
Accepted

## Context
ACPO Good Practice Guide Principle 1 requires that digital evidence handling be
auditable and that integrity be demonstrable at every access. Mutable custody
logs undermine court admissibility and make silent tampering difficult to detect.

## Decision
Persist chain-of-custody as an **append-only** ledger (`chain_of_custody` table,
no `updated_at`). `CustodyRepository` exposes insert/list/count APIs only — no
update or delete. `ChainOfCustodyService` records ACQUIRED as entry 1, verifies
integrity before ACCESS and SEAL actions, and detects sequential gaps / hash
drift in `verify_custody_chain`.

Every custody action dual-writes through `AuditService`. Closing a case seals
all linked evidence custody chains.

## Consequences
- Corrections require compensating append entries, never in-place edits.
- Integrity failures block ACCESS recording and surface via verification reports.
- Insert-only design simplifies forensic review and aligns with audit_log
  immutability from Prompt 2.
