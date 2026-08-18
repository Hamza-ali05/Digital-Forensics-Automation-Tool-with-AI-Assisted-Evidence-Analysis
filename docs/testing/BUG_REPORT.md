# DFAT Test Suite Bug Report (Prompt 9.13)

**Date:** 2026-08-18  
**Scope:** `make test-all`, `make test-contract`, `make frontend-test`, `make test-security`, plus validation/regression follow-up.

## Suite results

| Command | Result | Notes |
|---|---|---|
| `pytest tests/` (`make test-all`) | **793 passed**, 13 deselected | Performance tests skipped by default (`-m 'not performance'`) |
| `pytest tests/contract/` | Included above; all passed | |
| `pytest tests/security/` | Included above; all passed | |
| `pytest tests/validation/` | Included above; all passed | |
| `cd frontend && npm test -- --watchAll=false` | **93 passed** (27 suites) | `CI=true`, `NODE_OPTIONS=--openssl-legacy-provider` |
| `pytest tests/regression/` (`make test-regression`) | **15 passed** | Bug-fix + cross-layer contract tests |
| Playwright E2E | Included in `make test-full-suite` | Starts its own API + CRA servers. Optional skip: `DFAT_SKIP_E2E=1`. Ollama-marked performance tests are excluded from the full-suite performance step (`not requires_ollama`). |

No open failures remained after the fixes below. Deprecation warnings (Starlette TestClient/`httpx`, Pydantic `json_encoders`, passlib argon2 version) are non-blocking.

## Bugs found and fixed

### BUG-001 — Import error (`CASE_STATUS_TRANSITIONS`)

- **Category:** Import errors  
- **Symptom:** `POST /api/v1/cases/{id}/open` raised `NameError: name 'CASE_STATUS_TRANSITIONS' is not defined`.  
- **Cause:** `CaseService._validate_transition` used the transition map without importing it from `dfat.case_management.enums`.  
- **Fix:** Import `CASE_STATUS_TRANSITIONS` in `src/dfat/services/case_service.py`.  
- **Tests:** `test_bug_001_missing_case_status_transitions_import`, `test_regression_bug001_case_open_uses_transition_map`.

### BUG-002 — Stale audit logger in middleware

- **Category:** State errors  
- **Symptom:** `X-Request-ID` never appeared in the test audit JSONL; `AuditTrailMiddleware` kept the logger instance created at `create_app()` time.  
- **Cause:** Container overrides of `forensic_audit_logger` (used by tests and runtime wiring) were ignored by the middleware.  
- **Fix:** Resolve the logger from `request.app.state.container` on each request (`src/dfat/api/middleware/audit.py`).  
- **Tests:** `test_bug_002_audit_middleware_ignores_container_override`, `test_regression_bug002_request_id_reaches_container_audit_log`.

### BUG-003 — Stale `/health/ready` cache

- **Category:** State errors  
- **Symptom:** After simulating database failure then restore, `/api/v1/health/ready` still reported `database=false` for up to 10 seconds.  
- **Cause:** `ResponseCacheMiddleware` cached GET `/api/v1/health/ready` (TTL 10s).  
- **Fix:** Remove `/api/v1/health/ready` from `DEFAULT_CACHE_TTLS` so readiness probes always hit `HealthAggregator`. Liveness (`/health`) remains cached.  
- **Tests:** `test_bug_003_stale_readiness_cache`, `test_regression_bug003_readiness_reflects_live_database_state`, `test_readiness_path_is_not_cached`.

### BUG-004 — Unhandled ValueError on usability submit

- **Category:** Type errors  
- **Symptom:** `POST /api/v1/evaluation/usability/respond` with missing ratings raised `ValueError` (TestClient 500) instead of a client error.  
- **Cause:** `QuestionnaireInstrument._require_rating` raises `ValueError`; the evaluation route did not map it to HTTP.  
- **Fix:** Catch `ValueError` in `submit_usability_response` and return **422**.  
- **Tests:** `test_bug_004_usability_submit_unhandled_valueerror`, `test_regression_bug004_usability_validation_is_client_error`.

## Categories with no current defects

- **Async errors:** pytest-asyncio auto mode; no missing-await failures in the 793-test run.  
- **Frontend errors:** Jest suite green; `constants.js` / `permissions.js` match backend enums and `ROLE_PERMISSIONS`.

## Regression suite

`tests/regression/test_regression_suite.py` covers every bug above plus:

- `test_all_domain_models_serialisable`
- `test_all_orm_models_mappable`
- `test_all_repository_interfaces_implemented`
- `test_all_service_dependencies_resolvable`
- `test_all_api_routes_reachable`
- `test_frontend_constants_match_backend_enums`
- `test_frontend_permissions_match_backend_rbac`

Run with `make test-regression` or as part of `make test-full-suite`.
