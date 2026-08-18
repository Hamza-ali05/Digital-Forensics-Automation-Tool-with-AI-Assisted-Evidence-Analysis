# DFAT User Manual

This manual covers every investigator-facing feature in the DFAT web UI
(version 0.1.0). API equivalents are in
[API_REFERENCE.md](../development/API_REFERENCE.md). Getting started:
[QUICKSTART.md](QUICKSTART.md).

The UI is a React application at http://127.0.0.1:3000. Most pages require a
JWT session. Roles: **admin**, **investigator**, **analyst**, **viewer**.

## Sign in and account

| Page | Path | Who |
|------|------|-----|
| Login | `/auth/login` | Guests |
| Register | `/auth/register` | Guests (creates an account only if the API allows it; production registration is admin/investigator via the API) |
| Profile | `/profile` | Any authenticated user |
| Help | `/help` | Any authenticated user |

**Login.** Enter username and password. Failed attempts lock the account after
five failures for 30 minutes (configurable). Tokens refresh in the background.

**Profile.** View your username, email, role, and last login. Change password
(current password plus a new password of at least 12 characters).

**Logout.** Use the top bar. This revokes the current access token. Admins can
force a user to sign in again by deactivating the account.

## Roles at a glance

| Capability | admin | investigator | analyst | viewer |
|------------|-------|--------------|---------|--------|
| Manage users / settings / audit | yes | no | no | no |
| Create and transition cases | yes | yes | no | no |
| Register / quarantine evidence | yes | yes | no | no |
| Run pipeline and AI analysis | yes | yes | yes | no |
| View reports and evaluation | yes | yes | yes | yes |
| Administer usability export / delete | yes | results only | no | no |

Sidebar items you cannot use are hidden. API calls still enforce RBAC.

---

## Dashboard overview

Path: `/dashboard`. All authenticated roles.

The dashboard summarises operational health and recent work:

- **Stat cards** — case counts, evidence totals, pipeline jobs, reports.
- **Charts** — evidence by type/status and job status distribution when data exists.
- **Health bar** — readiness of database, local LLM, storage, pipeline, and audit
  logging (`GET /api/v1/health/ready`).
- **Shortcuts** — cases, evidence register, pipeline run, reports.

If you are a **viewer**, some cards stay empty because case and evidence APIs
are not in your permission set. Use **Reports** as the primary workspace.

---

## Case management workflow

Paths: `/cases`, `/cases/new`, `/cases/:id`.

Roles: list — admin, investigator, analyst; create and lifecycle — admin,
investigator.

### List and filter

**Cases** shows name, status, evidence count, and timestamps. Filter by status
or search by name. Open a row for the case detail page.

### Create

**New Case** requires a case name (1–255 characters) and optional description.
The new case is `created`. The creator is typically the lead investigator.

### Lifecycle

Allowed transitions:

```text
created → open → active → under_review → closed → archived
                ↘              ↗
                 └──── close ──┘   (from open or active)
under_review → active   (reopen, reason required)
```

On the case detail page:

1. **Open** — `created` → `open`. A lead investigator must be assigned.
2. **Activate** — `open` → `active`. Required before (or alongside) processing.
3. **Submit for review** — `active` → `under_review`.
4. **Reopen** — `under_review` → `active`. You must give a reason.
5. **Close** — seals linked evidence custody chains. Reason required.
6. **Archive** — `closed` → `archived`. Terminal state.

### Investigators and evidence

- Assign investigators as **lead** or **member**.
- Remove a member (soft-remove) from the investigators list.
- Link existing evidence IDs to the case, or register new evidence from the
  evidence workflow (preferred).

The **summary** tab aggregates investigators, evidence items, and notes.

---

## Evidence management workflow

Paths: `/evidence`, `/evidence/register`, `/evidence/integrity`, `/evidence/:id`.

### Inventory

**Evidence** lists registered items: file name, type (`disk_image` /
`memory_dump`), status, hashes, size, custody action count. Filter by case.

Statuses: `registered` → `validating` → `validated` → `processing` →
`processed` → `archived`. **Quarantined** is an operational hold.

### Register

**Register evidence** (`/evidence/register`):

1. Select an **open** or **active** case.
2. Enter the **server file path** (the API process must be able to read it).
3. Choose type and optional description.
4. Submit. DFAT computes hashes (SHA-256 primary, MD5 also stored), records an
   **acquired** custody action, and runs validation (size, MIME, format).

Do not use `..` in paths. Maximum size is configured (`max_evidence_size_gb`,
default 100).

A legacy API (`POST /api/v1/evidence`) still accepts `case_name` +
`investigator` for older clients; the UI uses `/evidence/register`.

### Detail, validate, quarantine

On **Evidence detail**:

- Re-run **validate**.
- View **status history**.
- View the **chain of custody** (append-only: acquired, accessed, analysed,
  transferred, released, sealed).
- **Quarantine** with a reason (investigator/admin). Quarantined evidence
  cannot be processed until it is returned to a processable state.

### Integrity check

**Integrity** (`/evidence/integrity`) re-hashes the file and compares stored
hashes. A match records an **accessed** custody action. Mismatches are flagged
as discrepancies — treat the item as compromised and quarantine it.

---

## Pipeline execution

Paths: `/pipeline`, `/pipeline/run`, `/pipeline/:jobId`.

Roles: admin, investigator, analyst.

### Submit a job

1. Choose case, evidence, and mode (`full` / `parse-only` / `triage-only`).
2. Optionally force **rule-based fallback** (no LLM).
3. Submit. Jobs are asynchronous.

The five stages are Acquisition, Parsing, AI Triage, Reporting, and Evaluation.
See [ARCHITECTURE.md](../architecture/ARCHITECTURE.md).

### Monitor and cancel

The jobs table filters by status (`queued`, `running`, `completed`, `failed`,
`cancelled`) and case. Job detail polls progress per stage (artefact counts,
parser results, errors, duration).

**Cancel** is allowed for the job owner or an admin while the job is queued or
running.

### Parsers

Admin **Settings** lists registered parsers and whether their native libraries
are available. Missing `pytsk3` or Volatility3 does not stop the pipeline; those
parsers are skipped.

---

## Artefacts, timeline, and IOCs

| Page | Path | Purpose |
|------|------|---------|
| Artefact explorer | `/artefacts/:id` | Category tabs, suspicion filter, artefact detail + AI explain |
| Timeline | `/artefacts/timeline` | Time-ordered artefacts with suspicion colouring |
| IOC dashboard | `/artefacts/iocs` | Extracted indicators from report / artefact data |

These pages need a completed parse/triage (or a report JSON). Analysts and
investigators use them to review filesystem, registry, browser, event log,
process, network, and injected-code artefacts.

---

## AI analysis usage

Paths: `/ai`, `/ai/summary`.

Requires `analysis:create` (admin, investigator, analyst) except the public
AI health probe.

**AI Analysis** (`/ai`):

- **Health** — whether Ollama is reachable (also shown on the dashboard).
- **Classify** — suspicion levels and reasoning for artefacts of an evidence ID.
  Use fallback if the LLM is down.
- **Summarise** — investigative summary of the artefact set.
- **Explain** — natural-language explanation of a single artefact (LLM required).
- **Ask** — investigator Q&A with optional conversation history. Answers are
  checked for hallucination risk against artefact evidence.

The structured JSON report remains the **evidential record**. LLM text is
advisory ([ADR-021](../architecture/adr/021-json-layer-primary-record.md)).

**AI Summary** (`/ai/summary`) shows the narrative layer from a selected report.

Admins can inspect AI usage stats and clear the response cache under
**Settings**.

---

## Report viewing and export

Paths: `/reports`, `/reports/json`, `/reports/:id`.

All roles with `reports:read` (including viewer).

### List and JSON viewer

The reports table is populated from completed pipeline jobs. **JSON viewer**
renders the structured report tree.

### Report detail

Tabs typically include:

- **Summary** — case name, generation time, pipeline duration.
- **JSON** — machine-readable evidential layer (schema-versioned).
- **Narrative** — human-readable summary (advisory).
- **Export** — PDF (or plaintext fallback if ReportLab is missing), self-contained
  HTML, and verified JSON file download.
- **Verify** — integrity hash, schema version, and report ID checks.
- **Custody** — chain-of-custody snapshot for the evidence.
- **Audit trail** — forensic actions recorded for the evidence/report.
- **Compare** — reproducibility check between two report IDs (artefact counts,
  hashes, suspicion distribution).

Treat JSON + hash verification as the court-facing package; PDF/HTML are
convenience exports.

---

## Benchmark evaluation

Paths: `/evaluation`, `/evaluation/benchmark`, `/evaluation/benchmark/history`,
`/evaluation/performance`.

Place ground-truth files under `data/ground_truth/` (or paths configured in
YAML). Dataset sources: `dfrws` and `cfreds`.

1. **Benchmark run** — pick evidence, dataset name, and source; run comparison.
2. **History** — precision, recall, F1, time-to-triage, false positives/negatives.
3. **Performance** — historical runs for a dataset name, optional baseline TTT.

Running a benchmark requires `evaluation:create` (admin, investigator). Viewing
results requires `evaluation:read`.

---

## Usability questionnaire administration

| Page | Path | Access |
|------|------|--------|
| Questionnaire (participant) | `/questionnaire` | **Public** — no login |
| Usability results | `/evaluation/usability` | admin, investigator |

The instrument is **immutable** at runtime ([ADR-023](../architecture/adr/023-questionnaire-immutability.md)).
Participants submit Likert ratings plus optional free text. Responses are
stored anonymously (participant ID only).

Investigators and admins review aggregate results. **Admins** can export JSON
and permanently delete all responses (ethics data destruction) via the API:

- `GET /api/v1/evaluation/usability/export`
- `DELETE /api/v1/evaluation/usability/responses`

Do not collect identifying data in the free-text field.

---

## User and role management (admin)

Paths: `/settings`, `/settings/users`, `/settings/audit`.

### Settings

Read-only operational view:

- Detailed health (uptime, table counts, package versions, component checks).
- AI engine health, cache statistics, **clear cache**.
- Parser inventory and availability.
- Database / configuration summary (no secret values displayed as editable).

### Users

- List all users (username, email, role, active flag, last login).
- **Register** a user: username, email, password (≥ 12 characters), full name,
  role (`admin` / `investigator` / `analyst` / `viewer`). Investigators may also
  register accounts via the API, but the UI registration modal is admin-only.
- **Deactivate** an account (cannot deactivate in a way that breaks your own
  last admin session without a recovery plan). Deactivated users cannot log in.

There is no “edit role” endpoint; assign the correct `role_name` at registration.

### Audit logs

Aggregated API and report audit trails with filters and CSV export. Dual-write
audit also lands in `data/outputs/audit.log` (JSONL) on the server.

---

## Errors and help

- **404 / 500** pages for missing routes and server failures.
- Request IDs appear as `X-Request-ID` on API responses; quote them when
  reporting bugs.
- In-app **Help** (`/help`) repeats the case → evidence → pipeline → report
  workflow and links to live OpenAPI docs when the API is running.
