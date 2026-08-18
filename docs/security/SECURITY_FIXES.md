# Security fixes (Prompt 9.10)

This note records hardening applied after Bandit review and the
`tests/security/` suite. All HIGH and MEDIUM Bandit findings are resolved
or explicitly suppressed with a documented reason. LOW findings remain
(mainly invariant `assert` statements, B101).

## Authentication

- **JWT algorithm confusion.** `JWTHandler.decode_token` inspects the
  unverified header and rejects missing, `none`, and non-`HS256`
  algorithms before signature verification.
- **Expired / malformed / revoked tokens.** Expired signatures map to 401,
  garbage tokens map to 401, and logout revokes the session JTI so reuse
  returns 401.
- **Disabled accounts.** `AccountDisabledError` is returned as HTTP 401
  (not 403) so a deactivated user's token cannot be distinguished as
  "valid but forbidden".
- **Brute-force lockout.** Five failed logins lock the account
  (`max_login_attempts=5`); further attempts, including the correct
  password, return 423.

## Authorisation

- **RBAC on every mutating route.** Write endpoints require
  `get_current_user` / `get_current_active_user` except documented public
  writes (`POST /auth/login`, `/auth/refresh`,
  `/evaluation/usability/respond`).
- **Role escalation.** Investigators (and other non-admins) cannot
  register a user with `role_name=admin`. JWT `role` claims are ignored
  for permission checks; the database role is authoritative.
- **Case isolation.** `GET /cases` lists only cases the caller created or
  is assigned to (admins see all). `GET /cases/{id}` and all case
  mutations call `CaseService.ensure_access` so investigators cannot
  read or alter another investigator's case.
- **Evidence delete.** `DELETE /api/v1/evidence/{id}` requires
  `evidence:delete` (analysts are read-only → 403).
- **Admin surfaces.** `/users` and `/health/detailed` remain admin-only.

## Injection and payloads

- **SQL search.** Case-name search uses SQLAlchemy `contains()` bound
  parameters; payloads such as `'; DROP TABLE cases; --` do not execute.
- **XSS.** Case names are stored and returned as JSON strings (plain
  text). They are not interpolated into HTML at the API boundary.
- **Path traversal.** `assert_no_path_traversal` rejects `..` segments
  (POSIX and Windows) and UNC prefixes on evidence `file_path` fields.
- **Request size.** `RequestValidationMiddleware` returns 413 when
  `Content-Length` exceeds 10 MiB.
- **Validation errors.** Pydantic `errors()` may contain exception
  objects; the global handler JSON-serializes them with `default=str`
  so traversal/validation failures return 422 instead of 500.

## HTTP hardening

- OWASP security headers on every response (`SecurityHeadersMiddleware`).
- CORS allow-list is `http://localhost:3000` and `http://127.0.0.1:3000`;
  other origins are not reflected.
- Auth endpoints are rate-limited (10 requests / minute / IP).
- Error payloads redact keys matching password, secret, token, traceback,
  stack, or exception.

## Local-only LLM

- `LLMConnectionManager` raises `ValueError` when `api_url` is not
  localhost / 127.0.0.1 / ::1 / 0.0.0.0.
- Classification (and generate) audit records store metadata only
  (counts, model, duration). Artefact bodies and prompt text are not
  written to the audit log.

## Bandit (HIGH / MEDIUM)

| ID | Location | Resolution |
| --- | --- | --- |
| B701 (HIGH) | `ai_engine/llm/prompts.py` Jinja2 `autoescape=False` | `# nosec B701`. Templates render LLM plaintext, not HTML; enabling HTML autoescape would mutate forensic artefact strings. |
| B104 (MEDIUM) | LLM local-host allow-lists (`0.0.0.0`) | `# nosec B104`. These strings identify *allowed local URLs*, they do not bind a server socket. |
| B104 (MEDIUM) | hallucination guard loopback skip | `# nosec B104`. Comparing parsed IPs to `0.0.0.0` / `127.0.0.1`. |
| B324 (MEDIUM) | `evidence_management/hash_service.py` MD5/SHA-1 | `# nosec B324`. Forensic multi-hash (MD5 + SHA-1 + SHA-256) is intentional defence-in-depth, not password hashing. |
| B608 (MEDIUM) | health detailed table counts | Replaced f-string SQL with a static mapping of `text("SELECT COUNT(*) FROM <literal_table>")` using an allow-list of table names. |

`make security-scan` writes `reports/bandit_report.json` and fails the
recipe when Bandit reports HIGH or MEDIUM findings (`bandit -ll`).

## Makefile

- `make security-scan` — Bandit JSON report + fail on HIGH/MEDIUM.
- `make test-security` — `pytest tests/security/ -v`.
