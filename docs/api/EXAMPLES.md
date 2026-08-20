# DFAT API Usage Examples

All examples use `curl` against a local development server at `http://localhost:8000`.

Set the base URL and retrieve a token first:

```bash
BASE=http://localhost:8000/api/v1
```

---

## Authentication

### Register

```bash
curl -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "analyst1",
    "email": "analyst1@example.com",
    "password": "Secure!Pass#2026",
    "full_name": "Jane Doe"
  }'
```

### Login

```bash
curl -X POST "$BASE/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Admin!Pass#2026"
```

Save the token:

```bash
TOKEN=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Admin!Pass#2026" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Refresh Token

```bash
curl -X POST "$BASE/auth/refresh" \
  -H "Authorization: Bearer $TOKEN"
```

### Logout

```bash
curl -X POST "$BASE/auth/logout" \
  -H "Authorization: Bearer $TOKEN"
```

### Logout All Sessions

```bash
curl -X POST "$BASE/auth/logout-all" \
  -H "Authorization: Bearer $TOKEN"
```

### Change Password

```bash
curl -X PUT "$BASE/auth/change-password" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"current_password": "Admin!Pass#2026", "new_password": "NewSecure!Pass#2026"}'
```

---

## Users

### Get Current User

```bash
curl "$BASE/users/me" -H "Authorization: Bearer $TOKEN"
```

### List All Users (Admin)

```bash
curl "$BASE/users" -H "Authorization: Bearer $TOKEN"
```

### Get User by ID (Admin)

```bash
curl "$BASE/users/1" -H "Authorization: Bearer $TOKEN"
```

### Deactivate User (Admin)

```bash
curl -X PUT "$BASE/users/1/deactivate" -H "Authorization: Bearer $TOKEN"
```

---

## Health

### Liveness Check

```bash
curl "$BASE/health"
```

### Readiness Check

```bash
curl "$BASE/health/ready"
```

### Detailed Health (Admin)

```bash
curl "$BASE/health/detailed" -H "Authorization: Bearer $TOKEN"
```

---

## Case Management

### Create Case

```bash
curl -X POST "$BASE/cases" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "case_name": "Investigation 001",
    "description": "Suspected data exfiltration from workstation",
    "case_type": "incident_response",
    "priority": "high"
  }'
```

### List Cases

```bash
curl "$BASE/cases" -H "Authorization: Bearer $TOKEN"
```

### List My Cases

```bash
curl "$BASE/cases/mine" -H "Authorization: Bearer $TOKEN"
```

### Get Case by ID

```bash
curl "$BASE/cases/1" -H "Authorization: Bearer $TOKEN"
```

### Get Case Summary

```bash
curl "$BASE/cases/1/summary" -H "Authorization: Bearer $TOKEN"
```

### Case Lifecycle Transitions

```bash
# Open
curl -X POST "$BASE/cases/1/open" -H "Authorization: Bearer $TOKEN"

# Activate
curl -X POST "$BASE/cases/1/activate" -H "Authorization: Bearer $TOKEN"

# Submit for review
curl -X POST "$BASE/cases/1/submit-review" -H "Authorization: Bearer $TOKEN"

# Reopen
curl -X POST "$BASE/cases/1/reopen" -H "Authorization: Bearer $TOKEN"

# Close
curl -X POST "$BASE/cases/1/close" -H "Authorization: Bearer $TOKEN"

# Archive
curl -X POST "$BASE/cases/1/archive" -H "Authorization: Bearer $TOKEN"
```

### Manage Investigators

```bash
# Add investigator
curl -X POST "$BASE/cases/1/investigators" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 2}'

# Remove investigator
curl -X DELETE "$BASE/cases/1/investigators/2" \
  -H "Authorization: Bearer $TOKEN"
```

### Link Evidence to Case

```bash
curl -X POST "$BASE/cases/1/evidence" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"evidence_id": 1}'
```

---

## Evidence (Legacy)

### Create Evidence

```bash
curl -X POST "$BASE/evidence" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "workstation-disk.dd",
    "file_path": "/evidence/workstation-disk.dd",
    "evidence_type": "disk_image",
    "hash_value": "abc123...",
    "hash_algorithm": "sha256"
  }'
```

### Get Evidence by ID

```bash
curl "$BASE/evidence/1" -H "Authorization: Bearer $TOKEN"
```

### List Evidence

```bash
curl "$BASE/evidence" -H "Authorization: Bearer $TOKEN"
```

### Delete Evidence

```bash
curl -X DELETE "$BASE/evidence/1" -H "Authorization: Bearer $TOKEN"
```

---

## Evidence Management

### Register Evidence

```bash
curl -X POST "$BASE/evidence/register" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "server-memory.raw",
    "file_path": "/evidence/server-memory.raw",
    "evidence_type": "memory_dump",
    "case_id": 1,
    "description": "Memory dump from compromised server"
  }'
```

### Evidence Inventory

```bash
curl "$BASE/evidence/inventory" -H "Authorization: Bearer $TOKEN"
```

### Evidence Statistics

```bash
curl "$BASE/evidence/statistics" -H "Authorization: Bearer $TOKEN"
```

### Evidence Detail

```bash
curl "$BASE/evidence/1/detail" -H "Authorization: Bearer $TOKEN"
```

### Validate Evidence

```bash
curl -X POST "$BASE/evidence/1/validate" \
  -H "Authorization: Bearer $TOKEN"
```

### Record Custody Transfer

```bash
curl -X POST "$BASE/evidence/1/custody" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "transfer",
    "handler_name": "Lab Analyst",
    "reason": "Transfer to analysis workstation"
  }'
```

### Get Custody Chain

```bash
curl "$BASE/evidence/1/custody" -H "Authorization: Bearer $TOKEN"
```

### Get Evidence Status

```bash
curl "$BASE/evidence/1/status" -H "Authorization: Bearer $TOKEN"
```

### Quarantine Evidence

```bash
curl -X POST "$BASE/evidence/1/quarantine" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Suspected contamination"}'
```

---

## Analysis

### Start Analysis

```bash
curl -X POST "$BASE/analysis" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"evidence_id": 1}'
```

### Get Analysis Status

```bash
curl "$BASE/analysis/pipeline-uuid-here" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Pipeline

### Submit Pipeline Job

```bash
curl -X POST "$BASE/pipeline" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "evidence_id": 1,
    "case_id": 1,
    "stages": ["acquisition", "parsing", "triage", "reporting"]
  }'
```

### List Jobs

```bash
curl "$BASE/pipeline/jobs" -H "Authorization: Bearer $TOKEN"
```

### List Available Parsers

```bash
curl "$BASE/pipeline/parsers" -H "Authorization: Bearer $TOKEN"
```

### Get Job Status

```bash
curl "$BASE/pipeline/job-uuid-here" -H "Authorization: Bearer $TOKEN"
```

### Get Job Progress

```bash
curl "$BASE/pipeline/job-uuid-here/progress" -H "Authorization: Bearer $TOKEN"
```

### Cancel Job

```bash
curl -X POST "$BASE/pipeline/job-uuid-here/cancel" \
  -H "Authorization: Bearer $TOKEN"
```

---

## AI Analysis

### Classify Artefacts

```bash
curl -X POST "$BASE/ai/classify" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "artefact_ids": ["artefact-uuid-1", "artefact-uuid-2"],
    "case_id": 1
  }'
```

### Summarise Investigation

```bash
curl -X POST "$BASE/ai/summarise" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"case_id": 1}'
```

### Explain Artefact

```bash
curl -X POST "$BASE/ai/explain" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"artefact_id": "artefact-uuid-1"}'
```

### Q&A

```bash
curl -X POST "$BASE/ai/qa" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What suspicious network connections were found?",
    "case_id": 1
  }'
```

### AI Health

```bash
curl "$BASE/ai/health" -H "Authorization: Bearer $TOKEN"
```

### AI Stats

```bash
curl "$BASE/ai/stats" -H "Authorization: Bearer $TOKEN"
```

### AI Cache Stats

```bash
curl "$BASE/ai/cache/stats" -H "Authorization: Bearer $TOKEN"
```

### Clear AI Cache

```bash
curl -X DELETE "$BASE/ai/cache" -H "Authorization: Bearer $TOKEN"
```

---

## Reports

### Get Report

```bash
curl "$BASE/reports/report-uuid" -H "Authorization: Bearer $TOKEN"
```

### Get Report JSON

```bash
curl "$BASE/reports/report-uuid/json" -H "Authorization: Bearer $TOKEN"
```

### Get Report Narrative

```bash
curl "$BASE/reports/report-uuid/narrative" -H "Authorization: Bearer $TOKEN"
```

### Export PDF

```bash
curl -o report.pdf "$BASE/reports/report-uuid/export/pdf" \
  -H "Authorization: Bearer $TOKEN"
```

### Export HTML

```bash
curl -o report.html "$BASE/reports/report-uuid/export/html" \
  -H "Authorization: Bearer $TOKEN"
```

### Export JSON File

```bash
curl -o report.json "$BASE/reports/report-uuid/export/json-file" \
  -H "Authorization: Bearer $TOKEN"
```

### Verify Report Integrity

```bash
curl -X POST "$BASE/reports/report-uuid/verify" \
  -H "Authorization: Bearer $TOKEN"
```

### Compare Reports (Reproducibility)

```bash
curl -X POST "$BASE/reports/compare" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"report_id_a": "uuid-a", "report_id_b": "uuid-b"}'
```

### Get Report Custody Chain

```bash
curl "$BASE/reports/report-uuid/custody" -H "Authorization: Bearer $TOKEN"
```

### Get Report Audit Trail

```bash
curl "$BASE/reports/report-uuid/audit-trail" -H "Authorization: Bearer $TOKEN"
```

---

## Evaluation

### Run Benchmark

```bash
curl -X POST "$BASE/evaluation/benchmark/run" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_name": "dfrws-2023",
    "artefact_ids": ["uuid-1", "uuid-2"]
  }'
```

### List Benchmark Results

```bash
curl "$BASE/evaluation/benchmark/results" -H "Authorization: Bearer $TOKEN"
```

### Get Benchmark Result

```bash
curl "$BASE/evaluation/benchmark/results/1" -H "Authorization: Bearer $TOKEN"
```

### Benchmark Performance Analysis

```bash
curl "$BASE/evaluation/benchmark/performance" -H "Authorization: Bearer $TOKEN"
```

### List Benchmark Datasets

```bash
curl "$BASE/evaluation/benchmark/datasets" -H "Authorization: Bearer $TOKEN"
```

### Submit Usability Response

```bash
curl -X POST "$BASE/evaluation/usability/submit" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "responses": [
      {"question_id": "sus_q1", "score": 4},
      {"question_id": "sus_q2", "score": 2}
    ]
  }'
```

### Get Usability Questionnaire

```bash
curl "$BASE/evaluation/usability/questionnaire" -H "Authorization: Bearer $TOKEN"
```

### Get Usability Results

```bash
curl "$BASE/evaluation/usability/results" -H "Authorization: Bearer $TOKEN"
```

### Export Usability CSV

```bash
curl -o usability.csv "$BASE/evaluation/usability/export" \
  -H "Authorization: Bearer $TOKEN"
```

### Delete Evaluation Data

```bash
curl -X DELETE "$BASE/evaluation/benchmark/results/1" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Monitoring

### Uptime (No Auth)

```bash
curl "$BASE/monitoring/uptime"
```

### Metrics (Admin)

```bash
curl "$BASE/monitoring/metrics?since_minutes=60" \
  -H "Authorization: Bearer $TOKEN"
```

### Logs (Admin)

```bash
curl "$BASE/monitoring/logs?level=ERROR&limit=50" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Pipeline Progress Polling Pattern

DFAT uses HTTP polling for pipeline progress monitoring:

```bash
# Submit job
JOB_ID=$(curl -s -X POST "$BASE/pipeline" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"evidence_id": 1, "case_id": 1}' | python -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# Poll progress every 5 seconds
while true; do
  STATUS=$(curl -s "$BASE/pipeline/$JOB_ID/progress" \
    -H "Authorization: Bearer $TOKEN")
  echo "$STATUS" | python -c "
import sys, json
p = json.load(sys.stdin)
print(f\"Stage: {p.get('current_stage','?')} | Progress: {p.get('percentage',0)}%\")
"
  DONE=$(echo "$STATUS" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))")
  if [ "$DONE" = "completed" ] || [ "$DONE" = "failed" ]; then
    echo "Pipeline $DONE"
    break
  fi
  sleep 5
done
```
