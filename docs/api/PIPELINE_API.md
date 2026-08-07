# Pipeline API

Base path: `/api/v1/pipeline`

All endpoints require a Bearer JWT unless noted. Permissions use the existing
RBAC resource `analysis` (`create` / `read` as indicated).

OpenAPI: interactive docs at `/docs` when the API is running.

Architecture overview: [`docs/architecture/PIPELINE.md`](../architecture/PIPELINE.md).

## Authentication

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

## Endpoints

### Submit pipeline job

`POST /api/v1/pipeline/run`

Permission: `analysis:create`  
Response: `202 Accepted`

Queues a job and runs it in a FastAPI background task.

**Request**

```json
{
  "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000",
  "case_id": "case-11111111-1111-1111-1111-111111111111",
  "mode": "full",
  "use_fallback": false
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `evidence_id` | string | yes | Registered evidence identifier |
| `case_id` | string | yes | Owning case identifier |
| `mode` | string | no | `full` (default), `parse-only`, or `triage-only` |
| `use_fallback` | boolean | no | Force rule-based triage (`false` default) |

**Response** (`PipelineJob`)

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000",
  "case_id": "case-11111111-1111-1111-1111-111111111111",
  "user_id": "user-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "status": "queued",
  "mode": "full",
  "use_fallback_analyzer": false,
  "created_at": "2026-08-07T08:00:00+00:00",
  "started_at": null,
  "completed_at": null,
  "total_duration_seconds": null,
  "current_stage": null,
  "stage_executions": {},
  "error_message": null,
  "artefact_count": 0,
  "report_id": null
}
```

---

### List jobs

`GET /api/v1/pipeline/jobs`

Permission: `analysis:read`

**Query parameters**

| Name | Type | Description |
|------|------|-------------|
| `status` | JobStatus | Optional filter (`queued`, `running`, `completed`, …) |
| `case_id` | string | Optional case filter |

**Example**

```http
GET /api/v1/pipeline/jobs?status=running&case_id=case-11111111-1111-1111-1111-111111111111
```

**Response**

```json
[
  {
    "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "evidence_id": "ev-550e8400-e29b-41d4-a716-446655440000",
    "case_id": "case-11111111-1111-1111-1111-111111111111",
    "user_id": "user-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "status": "running",
    "mode": "full",
    "use_fallback_analyzer": false,
    "created_at": "2026-08-07T08:00:00+00:00",
    "started_at": "2026-08-07T08:00:01+00:00",
    "completed_at": null,
    "total_duration_seconds": null,
    "current_stage": "parsing",
    "stage_executions": {},
    "error_message": null,
    "artefact_count": 120,
    "report_id": null
  }
]
```

---

### List parsers

`GET /api/v1/pipeline/parsers`

Permission: `analysis:read`

Returns registered parsers and whether their libraries are available in this
environment (frontend can disable unavailable categories).

**Response**

```json
{
  "parsers": [
    {
      "parser_name": "FileSystemParser",
      "available": true,
      "supported_evidence_types": ["disk_image"]
    },
    {
      "parser_name": "ProcessListParser",
      "available": false,
      "supported_evidence_types": ["memory_dump"]
    }
  ],
  "total": 2
}
```

---

### Get job

`GET /api/v1/pipeline/{job_id}`

Permission: `analysis:read`

Returns the full job including `stage_executions` and parser results once stages
have run.

**Response** (excerpt after parsing)

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "running",
  "current_stage": "ai_triage",
  "artefact_count": 1842,
  "stage_executions": {
    "parsing": {
      "stage": "parsing",
      "status": "completed",
      "started_at": "2026-08-07T08:00:05+00:00",
      "completed_at": "2026-08-07T08:02:10+00:00",
      "duration_seconds": 125.4,
      "output_summary": { "artefacts_total": 1842 },
      "errors": [],
      "parser_results": {
        "FileSystemParser": {
          "parser_name": "FileSystemParser",
          "status": "completed",
          "artefacts_found": 1500,
          "duration_seconds": 90.1,
          "error": null,
          "category": "filesystem_metadata"
        }
      }
    }
  },
  "report_id": null
}
```

**Errors**

| Status | When |
|--------|------|
| `404` | Unknown `job_id` (`JobNotFoundError`) |

---

### Get progress

`GET /api/v1/pipeline/{job_id}/progress`

Permission: `analysis:read`

Lightweight polling payload for progress UIs.

**Response**

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "running",
  "current_stage": "parsing",
  "stages_completed": 1,
  "stages_total": 5,
  "percent_complete": 20.0,
  "current_parser": "FileSystemParser",
  "elapsed_seconds": 45.2,
  "estimated_remaining_seconds": 180.0,
  "artefacts_found_so_far": 640
}
```

---

### Cancel job

`POST /api/v1/pipeline/{job_id}/cancel`

Permission: `analysis:create`, and caller must be the job owner or an admin.

Cancels a `queued` or `running` job.

**Response**

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "cancelled",
  "completed_at": "2026-08-07T08:01:00+00:00",
  "error_message": null
}
```

**Errors**

| Status | When |
|--------|------|
| `403` | Not owner/admin (`InsufficientPermissionsError`) |
| `404` | Unknown job |
| `409` / mapped cancel error | Job not cancellable (`JobCancellationError`) |

---

## Job status values

`queued` · `initialising` · `running` · `stage_complete` · `completed` · `failed` · `cancelled` · `timed_out`

## Frontend polling pattern

1. `POST /run` → store `job_id`.
2. Poll `GET /{job_id}/progress` every 1–2s while status is non-terminal.
3. On `completed`, fetch `GET /{job_id}` for stage details and `report_id`.
4. Load report JSON via existing report routes using `report_id`.
5. Optionally call `GET /parsers` once per session to grey-out unavailable parsers.

## Error envelope

Pipeline exceptions are mapped through the global API error handler. Typical body:

```json
{
  "error_type": "JobNotFoundError",
  "message": "Pipeline job not found: …",
  "timestamp": "2026-08-07T08:00:00+00:00",
  "details": {},
  "request_id": "…"
}
```
