# DFAT API Reference

Base URL: `http://127.0.0.1:8000/api/v1`

Interactive OpenAPI: `http://127.0.0.1:8000/docs` (ReDoc at `/redoc`).

This document matches the FastAPI routers mounted in `src/dfat/app.py`. Pipeline
narrative examples also live in [`docs/api/PIPELINE_API.md`](../api/PIPELINE_API.md).

## Conventions

### Authentication

Most endpoints require:

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

Obtain tokens with `POST /auth/login` (`application/x-www-form-urlencoded`).
Public endpoints: health liveness/readiness, login, refresh, AI health, and
usability questionnaire GET/POST.

### Roles (permission resource:action)

| Permission | admin | investigator | analyst | viewer |
|------------|-------|--------------|---------|--------|
| `cases:create` / `cases:update` | yes | yes | no | no |
| `cases:read` | yes | yes | yes | no |
| `evidence:create` / `update` / `delete` | yes | yes | no | no |
| `evidence:read` | yes | yes | yes | no |
| `analysis:create` / `analysis:read` | yes | yes | yes | no |
| `reports:read` | yes | yes | yes | yes |
| `evaluation:create` | yes | yes | no | no |
| `evaluation:read` | yes | yes | yes | yes |

`admin` has synthetic `all` CRUD. Some routes use `require_role([...])` instead
of a resource permission (noted per endpoint).

### Standard error body

```json
{
  "error_type": "InsufficientPermissionsError",
  "message": "Insufficient permissions",
  "timestamp": "2026-08-18T10:00:00+00:00",
  "details": {},
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

Correlate with the `X-Request-ID` response header.

| HTTP | Typical cause |
|------|----------------|
| 400 | Unsupported format, missing lead investigator, generic `DFATError` |
| 401 | Bad credentials, expired/revoked token, disabled account |
| 403 | Insufficient role/permission, quarantined evidence |
| 404 | Case, evidence, job, report, or ground-truth dataset missing |
| 409 | Invalid lifecycle transition, job already cancelled, integrity conflict |
| 422 | Validation (Pydantic or domain), all parsers failed, metrics error |
| 423 | Account locked |
| 429 | Rate limit (`Retry-After` header) |
| 500 | Pipeline stage or reporting failure |
| 503 | Parser libraries unavailable, local LLM unavailable |
| 504 | Pipeline stage timeout |

---

## Endpoint inventory

| Method | Path | Auth / permission | Description |
|--------|------|-------------------|-------------|
| GET | `/health` | Public | Liveness |
| GET | `/health/ready` | Public | Readiness checks |
| GET | `/health/detailed` | Role `admin` | Diagnostics |
| POST | `/auth/register` | Role `admin` or `investigator` | Create user |
| POST | `/auth/login` | Public | Issue tokens |
| POST | `/auth/refresh` | Public (refresh token) | Rotate tokens |
| POST | `/auth/logout` | Authenticated | Revoke current session |
| POST | `/auth/logout-all` | Authenticated | Revoke all sessions |
| PUT | `/auth/change-password` | Authenticated | Change password |
| GET | `/users/me` | Authenticated | Current profile |
| GET | `/users` | Role `admin` | List users |
| GET | `/users/{user_id}` | Role `admin` | Get user |
| PUT | `/users/{user_id}/deactivate` | Role `admin` | Deactivate user |
| POST | `/cases` | `cases:create` | Create case |
| GET | `/cases` | `cases:read` | List cases |
| GET | `/cases/mine` | `cases:read` | Cases for current user |
| GET | `/cases/{case_id}` | `cases:read` | Case detail |
| GET | `/cases/{case_id}/summary` | `cases:read` | Case summary |
| POST | `/cases/{case_id}/open` | `cases:update` | CREATED → OPEN |
| POST | `/cases/{case_id}/activate` | `cases:update` | OPEN → ACTIVE |
| POST | `/cases/{case_id}/submit-review` | `cases:update` | ACTIVE → UNDER_REVIEW |
| POST | `/cases/{case_id}/reopen` | `cases:update` | UNDER_REVIEW → ACTIVE |
| POST | `/cases/{case_id}/close` | `cases:update` | Close case |
| POST | `/cases/{case_id}/archive` | `cases:update` | CLOSED → ARCHIVED |
| POST | `/cases/{case_id}/investigators` | `cases:update` | Assign investigator |
| DELETE | `/cases/{case_id}/investigators/{user_id}` | `cases:update` | Remove investigator |
| POST | `/cases/{case_id}/evidence` | `cases:update` | Link evidence |
| POST | `/evidence/register` | `evidence:create` | Register and validate |
| GET | `/evidence/inventory` | `evidence:read` | Inventory |
| GET | `/evidence/statistics` | `evidence:read` | Aggregates |
| GET | `/evidence/{id}/detail` | `evidence:read` | Full detail |
| POST | `/evidence/{id}/validate` | `evidence:update` | Re-validate |
| POST | `/evidence/{id}/verify-integrity` | `evidence:read` | Re-hash |
| GET | `/evidence/{id}/custody` | `evidence:read` | Custody chain |
| GET | `/evidence/{id}/status` | `evidence:read` | Status history |
| POST | `/evidence/{id}/quarantine` | `evidence:update` | Quarantine |
| POST | `/evidence` | `evidence:create` | Legacy register |
| GET | `/evidence` | `evidence:read` | Legacy list |
| GET | `/evidence/{id}` | `evidence:read` | Legacy get |
| DELETE | `/evidence/{id}` | `evidence:delete` | Delete metadata |
| POST | `/analysis` | `analysis:create` | Sync analysis run |
| GET | `/analysis/{pipeline_id}` | `analysis:read` | Analysis status |
| POST | `/pipeline/run` | `analysis:create` | Async pipeline job |
| GET | `/pipeline/jobs` | `analysis:read` | List jobs |
| GET | `/pipeline/parsers` | `analysis:read` | Parser inventory |
| GET | `/pipeline/{job_id}` | `analysis:read` | Job detail |
| GET | `/pipeline/{job_id}/progress` | `analysis:read` | Progress |
| POST | `/pipeline/{job_id}/cancel` | `analysis:create` (owner or admin) | Cancel job |
| POST | `/ai/classify` | `analysis:create` | Classify artefacts |
| POST | `/ai/summarize` | `analysis:create` | Summarise evidence |
| POST | `/ai/explain/{artefact_id}` | `analysis:create` | Explain artefact |
| POST | `/ai/ask` | `analysis:create` | Investigator Q&A |
| GET | `/ai/health` | Public | LLM health |
| GET | `/ai/stats` | Role `admin` | AI usage stats |
| GET | `/ai/cache/stats` | Role `admin` | Cache stats |
| DELETE | `/ai/cache` | Role `admin` | Clear cache |
| POST | `/reports/compare` | `reports:read` | Reproducibility compare |
| GET | `/reports/{id}` | `reports:read` | Report summary |
| GET | `/reports/{id}/json` | `reports:read` | JSON layer |
| GET | `/reports/{id}/narrative` | `reports:read` | Narrative text |
| GET | `/reports/{id}/export/pdf` | `reports:read` | PDF/txt download |
| GET | `/reports/{id}/export/html` | `reports:read` | HTML download |
| GET | `/reports/{id}/export/json-file` | `reports:read` | JSON file download |
| POST | `/reports/{id}/verify` | `reports:read` | Integrity verify |
| GET | `/reports/{id}/custody` | `reports:read` | Custody report |
| GET | `/reports/{id}/audit-trail` | `reports:read` | Audit report |
| POST | `/evaluation/benchmark` | `evaluation:create` | Run benchmark |
| GET | `/evaluation/benchmark/results` | `evaluation:read` | List results |
| GET | `/evaluation/benchmark/results/{id}` | `evaluation:read` | One result |
| GET | `/evaluation/benchmark/performance` | `evaluation:read` | Performance analytics |
| GET | `/evaluation/benchmark/datasets` | `evaluation:read` | Dataset names |
| GET | `/evaluation/results` | `evaluation:read` | Legacy list (hidden) |
| POST | `/evaluation/usability/respond` | Public | Submit questionnaire |
| GET | `/evaluation/usability/questionnaire` | Public | Instrument JSON |
| GET | `/evaluation/usability/results` | Role `admin` or `investigator` | Analysis |
| GET | `/evaluation/usability/export` | Role `admin` | Export JSON |
| DELETE | `/evaluation/usability/responses` | Role `admin` | Ethics delete |

---

## Health

### GET `/health`

**Auth:** none. **Response 200:**

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-08-18T10:00:00+00:00"
}
```

### GET `/health/ready`

**Auth:** none. Aggregates database, LLM, storage, pipeline (stuck jobs), and
audit writability. Overall `status` is `ready`, `degraded`, or `unavailable`.

```json
{
  "status": "ready",
  "checks": {
    "database": true,
    "llm": true,
    "storage": true,
    "pipeline": true,
    "audit": true
  },
  "timestamp": "2026-08-18T10:00:00+00:00"
}
```

### GET `/health/detailed`

**Auth:** role `admin`. Adds uptime, Python/platform, package versions, table
counts, memory, and the same component `checks`. **Errors:** 401, 403.

---

## Auth

### POST `/auth/register`

**Auth:** role `admin` or `investigator`. **Status:** 201.

```json
{
  "username": "analyst2",
  "email": "analyst2@example.com",
  "password": "StrongPass#2026",
  "full_name": "Second Analyst",
  "role_name": "analyst"
}
```

`role_name` defaults to `analyst`. Password minimum length is 12.

**Response:** `UserResponse` (id, username, email, full_name, role_name,
is_active, last_login, created_at). **Errors:** 401, 403, 422.

### POST `/auth/login`

**Auth:** none. **Body:** `application/x-www-form-urlencoded`

```text
username=admin&password=Admin!Pass#2026
```

**Response 200:**

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Errors:** 401 invalid credentials, 423 locked, 401 disabled.

### POST `/auth/refresh`

```json
{ "refresh_token": "<jwt>" }
```

**Response:** same as login. **Errors:** 401 expired/revoked.

### POST `/auth/logout`

**Auth:** bearer. **Status:** 204. Revokes current access-token `jti`.

### POST `/auth/logout-all`

**Auth:** bearer. **Response 200:** `{ "revoked_count": 2 }`

### PUT `/auth/change-password`

```json
{
  "current_password": "Admin!Pass#2026",
  "new_password": "Admin!Pass#2027"
}
```

**Status:** 204. **Errors:** 401, 422.

---

## Users

### GET `/users/me`

**Auth:** any active user. **Response:** `UserResponse`.

### GET `/users`

**Auth:** admin. **Response:** array of `UserResponse`.

### GET `/users/{user_id}`

**Auth:** admin. **Errors:** 404.

### PUT `/users/{user_id}/deactivate`

**Auth:** admin. **Status:** 204.

---

## Cases

Case statuses: `created`, `open`, `active`, `under_review`, `closed`, `archived`.

Shared `CaseResponse` example:

```json
{
  "case_id": "case-11111111-1111-1111-1111-111111111111",
  "case_name": "Operation Example",
  "description": "Disk image from workstation 14",
  "status": "open",
  "lead_investigator_id": "user-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "investigators": [
    {
      "user_id": "user-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      "username": "admin",
      "full_name": "DFAT Administrator",
      "role": "lead",
      "assigned_at": "2026-08-18T10:00:00+00:00"
    }
  ],
  "evidence_ids": [],
  "evidence_count": 0,
  "investigator_count": 1,
  "opened_at": "2026-08-18T10:05:00+00:00",
  "closed_at": null,
  "archived_at": null,
  "closure_reason": null,
  "notes": [],
  "tags": [],
  "created_at": "2026-08-18T10:00:00+00:00"
}
```

List wrapper: `{ "cases": [CaseResponse], "total": 1 }`.

**Errors (lifecycle):** 400 no lead investigator, 404, 409 invalid transition.

### POST `/cases`

```json
{ "case_name": "Operation Example", "description": "Optional" }
```

**Status:** 201.

### GET `/cases`

Query: `status` (enum), `search` (case name, max 200).

### GET `/cases/mine`

Cases where the caller is an active investigator.

### GET `/cases/{case_id}` / GET `/cases/{case_id}/summary`

Summary adds `evidence_summaries` and string timestamps.

### POST `/cases/{case_id}/open` · `/activate` · `/submit-review` · `/archive`

Empty body. Open requires a lead investigator.

### POST `/cases/{case_id}/reopen` · `/close`

```json
{ "reason": "Additional artefacts recovered" }
```

`reason` is required (min length 1).

### POST `/cases/{case_id}/investigators`

```json
{ "user_id": "user-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "role": "member" }
```

`role` is `lead` or `member` (default `member`).

### DELETE `/cases/{case_id}/investigators/{user_id}`

Soft-remove. **Response:** updated `CaseResponse`.

### POST `/cases/{case_id}/evidence`

```json
{ "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000" }
```

---

## Evidence management

Preferred workflow. Router prefix `/evidence`; static paths are registered
**before** the legacy `/{evidence_id}` route.

`evidence_type`: `disk_image` | `memory_dump`.

### POST `/evidence/register`

**Status:** 201. Case must be open or active.

```json
{
  "file_path": "data/evidence/sample.dd",
  "case_id": "case-11111111-1111-1111-1111-111111111111",
  "evidence_type": "disk_image",
  "description": "Workstation 14 disk"
}
```

**Response (`EvidenceValidationResponse`):**

```json
{
  "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000",
  "validation_passed": true,
  "metadata": {},
  "custody_record": {},
  "validation_failures": [],
  "case_id": "case-11111111-1111-1111-1111-111111111111"
}
```

**Errors:** 400 unsupported format / traversal, 404 case, 409 case not open,
422 validation.

### GET `/evidence/inventory`

Query: `case_id` (optional). **Response:** `{ "items": [...], "total": 1 }` with
file name, type, status, hash_set, mime_type, size, timestamps, custody count.

### GET `/evidence/statistics`

Query: `case_id` optional. **Response:** totals by type/status, `total_size`,
`avg_custody_chain_length`.

### GET `/evidence/{evidence_id}/detail`

Hashes, case, status history, custody chain.

### POST `/evidence/{evidence_id}/validate`

Re-runs validation. **Response:** `EvidenceValidationResponse`.

### POST `/evidence/{evidence_id}/verify-integrity`

**Response:**

```json
{
  "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000",
  "integrity_verified": true,
  "hash_set": { "sha256": "abc…", "md5": "def…" },
  "timestamp": "2026-08-18T10:00:00+00:00",
  "discrepancies": {},
  "custody_record": {}
}
```

### GET `/evidence/{evidence_id}/custody`

```json
{
  "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000",
  "entries": [
    {
      "entry_number": 1,
      "record_id": "cust-1",
      "action": "acquired",
      "performed_by_user_id": "user-aaa",
      "performed_by_name": "DFAT Administrator",
      "timestamp": "2026-08-18T10:00:00+00:00",
      "reason": "Initial registration",
      "hash_at_action": "abc…",
      "location": "DFAT Local System",
      "notes": null
    }
  ],
  "total_entries": 1
}
```

### GET `/evidence/{evidence_id}/status`

Current status plus history of `previous_status` / `new_status` / actor / reason.

### POST `/evidence/{evidence_id}/quarantine`

```json
{ "reason": "Hash mismatch on re-verification" }
```

**Errors:** 403 if already blocked by quarantine rules, 409 invalid transition.

---

## Evidence (legacy)

### POST `/evidence`

```json
{
  "file_path": "data/evidence/sample.dd",
  "case_name": "Operation Example",
  "investigator": "admin",
  "description": "Optional",
  "evidence_type": "disk_image"
}
```

**Status:** 201. **Response:** `evidence_id`, `file_path`, `evidence_type`,
`original_hash`, `case` object, `registered_by`.

### GET `/evidence` · GET `/evidence/{evidence_id}`

List or fetch legacy `EvidenceResponse`.

### DELETE `/evidence/{evidence_id}`

**Status:** 204. Deletes metadata (not necessarily the raw file).

---

## Analysis (synchronous)

Companion to the async pipeline. Prefer `POST /pipeline/run` for UI jobs.

### POST `/analysis`

**Status:** 202.

```json
{
  "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000",
  "mode": "full",
  "use_fallback": false
}
```

`mode`: `full` | `parse-only` | `triage-only`.

**Response:**

```json
{
  "pipeline_id": "…",
  "current_stage": "reporting",
  "is_complete": true,
  "stage_results": {},
  "errors": []
}
```

### GET `/analysis/{pipeline_id}`

Same `AnalysisStatusResponse`. **Errors:** 404.

---

## Pipeline (asynchronous)

### POST `/pipeline/run`

**Status:** 202. Queues a background job.

```json
{
  "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000",
  "case_id": "case-11111111-1111-1111-1111-111111111111",
  "mode": "full",
  "use_fallback": false
}
```

**Response (`PipelineJob`):** `job_id`, ids, `status` (`queued`), `mode`,
`use_fallback_analyzer`, timestamps, `current_stage`, `stage_executions`,
`error_message`, `artefact_count`, `report_id`.

### GET `/pipeline/jobs`

Query: `status`, `case_id`. **Response:** array of `PipelineJob`.

### GET `/pipeline/parsers`

```json
{
  "parsers": [
    {
      "parser_name": "FileSystemParser",
      "available": true,
      "supported_evidence_types": ["disk_image"]
    }
  ],
  "total": 8
}
```

### GET `/pipeline/{job_id}` · GET `/pipeline/{job_id}/progress`

Progress includes per-stage percent complete and current parser. **Errors:** 404.

### POST `/pipeline/{job_id}/cancel`

Job **owner** or **admin**. **Errors:** 403, 409 if not cancellable.

---

## AI analysis

LLM calls fail with **503** (`AIEngineError` / `LLMConnectionError`) if Ollama
is down and `use_fallback` is not set. Classify/summarise support fallback.

### POST `/ai/classify`

```json
{ "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000", "use_fallback": false }
```

**Response:** `{ "classifications": [...], "confidence": 0.8, "model_used": "llama3", "analysis_record_id": "…" }`

**Errors:** 404 no artefacts.

### POST `/ai/summarize`

Same request shape as classify. **Response:** `{ "summary": { "full_text": "…", "executive_summary": "…", "model_used": "llama3", "prompt_version": "…", "confidence_score": 0.7 }, "analysis_record_id": "…" }`

### POST `/ai/explain/{artefact_id}`

No body. LLM required. **Response:** `{ "explanation": { "explanation_text": "…", "confidence": 0.7, "model_used": "llama3" }, "analysis_record_id": "…" }`

### POST `/ai/ask`

```json
{
  "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000",
  "question": "Which processes have external network connections?",
  "conversation_history": [{ "role": "user", "content": "List suspicious processes" }]
}
```

**Response:** Q&A payload including answer, confidence, optional hallucination
check, plus `analysis_record_id`.

### GET `/ai/health`

**Auth:** none. LLM connectivity (`available`, latency, model).

### GET `/ai/stats` · GET `/ai/cache/stats` · DELETE `/ai/cache`

**Auth:** admin. DELETE returns `{ "cleared_entries": 12, "cleared_at": "…" }`.

---

## Reports

### POST `/reports/compare`

```json
{
  "report_id_a": "rpt-aaa",
  "report_id_b": "rpt-bbb"
}
```

**Response:** `is_reproducible`, hashes, count/distribution match flags,
`differences`, `verified_at`.

### GET `/reports/{report_id}`

```json
{
  "report_id": "rpt-aaa",
  "case_name": "Operation Example",
  "json_report_url": "/api/v1/reports/rpt-aaa/json",
  "narrative_report_url": "/api/v1/reports/rpt-aaa/narrative",
  "generated_at": "2026-08-18T11:00:00+00:00",
  "pipeline_duration_seconds": 42.5
}
```

### GET `/reports/{report_id}/json`

Full JSON report document (artefacts, rankings, hashes, schema version).

### GET `/reports/{report_id}/narrative`

`text/plain` — `summary_text` only.

### GET `/reports/{report_id}/export/pdf` · `/export/html` · `/export/json-file`

File downloads. PDF may fall back to `.txt` if ReportLab is unavailable.

### POST `/reports/{report_id}/verify`

```json
{
  "is_valid": true,
  "integrity_hash_match": true,
  "schema_version_valid": true,
  "report_id_valid": true,
  "issues": [],
  "verified_at": "2026-08-18T11:05:00+00:00"
}
```

### GET `/reports/{report_id}/custody` · `/audit-trail`

JSON custody / audit trail documents for the report’s evidence.

**Errors:** 404 unknown report.

---

## Evaluation

### POST `/evaluation/benchmark`

```json
{
  "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000",
  "ground_truth_dataset": "dfrws-2006",
  "dataset_source": "dfrws"
}
```

`dataset_source`: `dfrws` | `cfreds`. Legacy fields `ground_truth_path` and
`dataset_name` are accepted.

**Response:**

```json
{
  "benchmark_id": "bm-1",
  "dataset_name": "dfrws-2006",
  "precision": 0.8,
  "recall": 0.7,
  "f1_score": 0.75,
  "time_to_triage_seconds": 12.4,
  "artefacts_expected": 100,
  "artefacts_recovered": 80,
  "false_positives": 5,
  "false_negatives": 20,
  "evaluated_at": "2026-08-18T12:00:00+00:00"
}
```

**Errors:** 404 ground truth missing, 422 metrics calculation.

### GET `/evaluation/benchmark/results` · `/evaluation/benchmark/results/{benchmark_id}`

List or fetch `BenchmarkResponse`. Legacy alias `GET /evaluation/results` is
hidden from OpenAPI but still served.

### GET `/evaluation/benchmark/performance`

Query: `dataset_name` (required), `baseline_ttt` (optional, > 0).

### GET `/evaluation/benchmark/datasets`

```json
{ "dfrws": ["dfrws-2006"], "cfreds": [] }
```

### POST `/evaluation/usability/respond`

**Auth:** none. **Status:** 201.

```json
{
  "ratings": { "q1": 5, "q2": 4 },
  "free_text": "Optional comment"
}
```

Invalid ratings return **422**. **Response:** `{ "participant_id": "…", "message": "Response collected anonymously." }`

### GET `/evaluation/usability/questionnaire`

**Auth:** none. Frozen instrument definition.

### GET `/evaluation/usability/results`

**Auth:** admin or investigator. Aggregate analysis.

### GET `/evaluation/usability/export`

**Auth:** admin. JSON document of anonymised responses.

### DELETE `/evaluation/usability/responses`

**Auth:** admin. `{ "deleted_count": 12 }` — ethics destruction.
