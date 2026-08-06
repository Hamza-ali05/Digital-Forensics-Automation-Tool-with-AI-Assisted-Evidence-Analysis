# ADR-008: JWT Authentication with RBAC

## Status
Accepted

## Context
ACPO Principle 4 requires accountability for investigative actions. The forensic API must identify users and constrain actions by role.

## Decision
Add local JWT authentication with role-based access control:
- Roles: `admin`, `investigator`, `analyst`, `viewer`.
- Tokens issued and validated locally (no external IdP required for the prototype).
- New auth exceptions (`AuthenticationError`, `AuthorisationError`, `TokenExpiredError`) extend `DFATError` without modifying existing exception types.

## Consequences
- New `auth/` package and API routes (`/auth`, `/users`).
- Audit trail can attribute actions to authenticated investigators.
- Passwords hashed with Argon2/bcrypt; secrets stay in local config/env.
