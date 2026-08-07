# ADR-008: JWT Authentication with RBAC

## Status
Accepted

## Context
ACPO Principle 4 requires investigator accountability. Multi-user access to
the forensic tool necessitates authenticated, role-gated operations on evidence
metadata, analysis runs, and reports.

## Decision
Implement local JWT authentication with role-based access control:

- **Roles:** `admin`, `investigator`, `analyst`, `viewer` (seeded in migration `001`).
- **Tokens:** Access and refresh JWT pairs; issued and validated locally (no
  external IdP for the prototype).
- **Sessions:** JTI tracked in `user_sessions`; revocation on logout/password change.
- **Lockout:** Account locked after `max_login_attempts` failed logins.
- **RBAC:** `ROLE_PERMISSIONS` hardcoded in `auth/rbac.py`, matching seed data.

Auth exceptions extend `DFATError` in `auth/exceptions.py` without modifying
`core/exceptions.py`.

## Consequences
- Every API endpoint except health checks and public auth routes (`/auth/login`,
  `/auth/refresh`) requires authentication.
- Audit log entries include `user_id` when a valid Bearer token is present.
- Role permissions are hardcoded for simplicity; changing roles requires code
  and migration alignment.
- Passwords hashed with Argon2 (preferred) / bcrypt fallback; secrets in
  `config/` and `DFAT_AUTH__*` environment variables.
