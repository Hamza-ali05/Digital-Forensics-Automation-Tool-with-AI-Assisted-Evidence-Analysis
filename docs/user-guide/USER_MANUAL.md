# DFAT User Manual

**Digital Forensics Automation Tool with AI-Assisted Evidence Analysis**

Version 0.1.0 | Canterbury Christ Church University | MSc Cybersecurity

---

## Table of Contents

1. [Getting Started](#chapter-1--getting-started)
2. [Case Management](#chapter-2--case-management)
3. [Evidence Management](#chapter-3--evidence-management)
4. [Running the Forensic Pipeline](#chapter-4--running-the-forensic-pipeline)
5. [Exploring Artefacts](#chapter-5--exploring-artefacts)
6. [AI-Assisted Analysis](#chapter-6--ai-assisted-analysis)
7. [Reports](#chapter-7--reports)
8. [Benchmark Evaluation](#chapter-8--benchmark-evaluation)
9. [Usability Questionnaire](#chapter-9--usability-questionnaire)
10. [Administration](#chapter-10--administration)

---

## Chapter 1 — Getting Started

### 1.1 Logging In

Navigate to the DFAT web interface (default: `http://localhost:3000`). You will see the login page.

1. Enter your **username** and **password**.
2. Click **Login**.
3. On first use, the default admin account is available (credentials provided by your administrator).

New users can be created by an admin via the User Management page, or via the **Register** page if self-registration is enabled.

### 1.2 Dashboard Overview

After login, you land on the **Dashboard** page, which displays:

- **Active Cases** — count of open investigations
- **Total Evidence** — registered evidence items
- **Pipeline Jobs** — recent and running analysis jobs
- **Quick Actions** — buttons to create a case, register evidence, or start a pipeline run
- **Recent Activity** — timeline of recent system events

### 1.3 Understanding Your Role

DFAT uses role-based access control (RBAC) with four roles:

| Role | Permissions |
|------|------------|
| **Admin** | Full access: user management, system settings, audit logs, all cases |
| **Investigator** | Create/manage cases, register evidence, run pipelines, view reports |
| **Analyst** | View assigned cases, run AI analysis, view artefacts and reports |
| **Viewer** | Read-only access to cases and reports assigned to them |

Your role determines which navigation items and actions are available.

### 1.4 Navigation Guide

The sidebar navigation provides access to all sections:

- **Dashboard** — overview and quick actions
- **Cases** — investigation case management
- **Evidence** — evidence registration and inventory
- **Pipeline** — forensic analysis pipeline
- **Artefacts** — artefact explorer, timeline, IOC dashboard
- **AI Analysis** — AI-assisted classification and Q&A
- **Reports** — forensic report viewing and export
- **Evaluation** — benchmark and usability evaluation
- **Settings** — profile and system settings (admin)
- **Help** — contextual help and documentation links

---

## Chapter 2 — Case Management

### 2.1 Creating a New Investigation Case

1. Navigate to **Cases > Create Case** or click the quick action on the Dashboard.
2. Fill in the required fields:
   - **Case Name** — a descriptive title (e.g., "Incident Response — Workstation 42")
   - **Description** — details of the investigation
   - **Case Type** — select from incident response, malware analysis, data recovery, etc.
   - **Priority** — low, medium, high, or critical
3. Click **Create Case**.

The case is created in **draft** status.

### 2.2 Assigning Investigators

1. Open a case from the case list.
2. In the **Investigators** section, click **Add Investigator**.
3. Select a user from the list.
4. The first investigator added is typically the lead investigator.

To remove an investigator, click the remove icon next to their name.

### 2.3 Case Lifecycle

Cases follow a defined lifecycle:

```
Draft → Open → Active → Under Review → Closed → Archived
                  ↑            |
                  └── Reopen ──┘
```

| Transition | Action | Who |
|-----------|--------|-----|
| Draft → Open | Click **Open Case** | Case owner / admin |
| Open → Active | Click **Activate** | Lead investigator |
| Active → Under Review | Click **Submit for Review** | Lead investigator |
| Under Review → Closed | Click **Close Case** | Admin / reviewer |
| Closed → Archived | Click **Archive** | Admin |
| Under Review → Active | Click **Reopen** | Admin / lead |

Each transition is recorded in the audit trail.

### 2.4 Viewing Case Summary

The **Case Summary** page shows:

- Case metadata (name, type, priority, status, dates)
- Assigned investigators
- Linked evidence items
- Pipeline runs and their status
- Activity log with timestamped events

### 2.5 Linking Evidence to a Case

1. Open the case detail page.
2. Click **Link Evidence**.
3. Select from registered evidence items.
4. The evidence is now associated with the case and visible in the case summary.

---

## Chapter 3 — Evidence Management

### 3.1 Registering Forensic Evidence

Evidence files (disk images, memory dumps) must be placed in the configured evidence directory before registration.

1. Navigate to **Evidence > Register Evidence**.
2. Fill in:
   - **Name** — descriptive name (e.g., "workstation-42-disk.dd")
   - **File Path** — path to the evidence file within the evidence directory
   - **Evidence Type** — disk image or memory dump
   - **Case** — optionally associate with a case
   - **Description** — additional context
3. Click **Register**.

DFAT automatically computes hash values and performs initial validation.

### 3.2 Understanding Evidence Types

| Type | Description | Parsers Used |
|------|------------|-------------|
| **Disk Image** | Raw or forensic disk image (.dd, .E01, .raw) | Filesystem, Registry, Browser History, Event Log |
| **Memory Dump** | RAM capture (.raw, .mem, .vmem) | Process List, Network Connections, Code Injection, Memory Registry |

### 3.3 Evidence Validation and MIME Type Verification

After registration, DFAT validates:

- File exists and is readable
- MIME type matches declared evidence type
- File size is within acceptable range
- File is not corrupted (header check)

View validation results on the **Evidence Detail** page.

### 3.4 Viewing Hash Sets

DFAT computes three hash values for every evidence item:

- **MD5** — for legacy compatibility
- **SHA-1** — for comparison with existing databases
- **SHA-256** — primary integrity hash (forensically preferred)

All hashes are displayed on the Evidence Detail page and recorded in the audit trail.

### 3.5 Evidence Integrity Verification

1. Navigate to the evidence detail page.
2. Click **Verify Integrity** (or visit the Integrity Check page).
3. DFAT recomputes hash values and compares against the stored originals.
4. Results show **PASS** or **FAIL** for each algorithm.

This process verifies the evidence has not been modified since registration.

### 3.6 Chain-of-Custody Tracking

Every action on evidence is recorded in the chain of custody:

- Registration and initial hashing
- Transfers between handlers
- Pipeline processing events
- Validation checks
- Quarantine actions

View the full chain on the **Evidence Detail > Custody** tab.

### 3.7 Evidence Status Lifecycle

```
Registered → Validated → Processing → Analysed
                                        ↓
                              Quarantined (if issues found)
```

The current status is visible on the Evidence Detail page and in the inventory.

### 3.8 Evidence Inventory and Filtering

The **Evidence Inventory** page shows all registered evidence with:

- Name, type, status
- Hash values
- Associated case
- Registration date

Use the filter and search controls to find specific items.

### 3.9 Evidence Statistics

The **Evidence Statistics** view provides aggregate metrics:

- Total evidence items by type
- Status distribution
- Storage utilisation
- Validation pass/fail rates

---

## Chapter 4 — Running the Forensic Pipeline

### 4.1 Starting a Pipeline Run

1. Navigate to **Pipeline > Run Pipeline**.
2. Select the **evidence** to analyse.
3. Select the **case** to associate results with.
4. Choose analysis stages (defaults to all five):
   - Acquisition
   - Parsing
   - Triage
   - Reporting
   - Evaluation
5. Click **Submit Job**.

The job is queued and begins processing.

### 4.2 Understanding Pipeline Stages

The five-stage pipeline processes evidence sequentially:

**Stage 1 — Acquisition**
Loads the evidence file, verifies integrity, and prepares it for parsing. Records custody transfer to the processing system.

**Stage 2 — Parsing**
Routes evidence to appropriate parsers based on type. Disk images are parsed for filesystem entries, registry keys, browser history, and event logs. Memory dumps are analysed for processes, network connections, and code injection. Artefacts are normalised into a standard format.

**Stage 3 — Triage**
Applies rule-based scoring to all artefacts. IOC detection identifies indicators of compromise. AI analysis (if enabled) classifies artefacts and generates an investigative summary. Results are aggregated and prioritised by suspicion score.

**Stage 4 — Reporting**
Generates dual-output forensic reports:
- **Structured JSON** — machine-readable, schema-validated
- **Narrative** — human-readable investigative narrative

Reports include integrity hashes and metadata for reproducibility.

**Stage 5 — Evaluation**
Optionally compares results against ground truth datasets (DFRWS/CFReDS) and computes precision, recall, and F1 metrics.

### 4.3 Monitoring Pipeline Progress

The **Pipeline Detail** page shows real-time progress:

- Current stage and percentage complete
- Stage-by-stage timing
- Artefact counts as they are discovered
- Error or warning messages

Poll the progress endpoint or refresh the page to see updates.

### 4.4 Interpreting Parser Results

After parsing completes, results show:

- **Artefact count** per parser
- **Parser status** (success, partial, failed)
- **Warnings** for parsers that encountered non-fatal issues

### 4.5 Handling Pipeline Failures

If a pipeline job fails:

1. Check the **Pipeline Detail** page for the error message.
2. Review the stage that failed and its logs.
3. Common causes:
   - Unsupported evidence format
   - Corrupted evidence file
   - Insufficient disk space
   - Ollama not running (for AI triage)
4. Fix the issue and submit a new job.

You can **cancel** a running job from the Pipeline Jobs page.

---

## Chapter 5 — Exploring Artefacts

### 5.1 Using the Artefact Explorer

Navigate to **Artefacts > Explorer** to browse all discovered artefacts. The explorer provides:

- Sortable table of artefacts
- Column visibility controls
- Expandable detail rows

### 5.2 Filtering by Category and Suspicion Level

Use the filter controls to narrow results:

- **Category** — filesystem, registry, browser, event_log, process, network, injection
- **Suspicion Level** — critical, high, medium, low, benign
- **Source Parser** — which parser discovered the artefact
- **Date Range** — filter by artefact timestamp

### 5.3 Understanding Suspicion Scores

Each artefact receives a **suspicion score** from 0 to 100:

| Score Range | Level | Meaning |
|------------|-------|---------|
| 80–100 | Critical | Strong indicators of malicious activity |
| 60–79 | High | Suspicious activity requiring investigation |
| 40–59 | Medium | Potentially anomalous, warrants review |
| 20–39 | Low | Likely benign but flagged by a rule |
| 0–19 | Benign | Normal system activity |

Scores are determined by rule-based triage and optionally refined by AI classification.

### 5.4 Disk Artefacts

**Filesystem** — files with metadata (path, size, timestamps, permissions). Highlights recently modified, hidden, or executable files in unusual locations.

**Registry** — Windows registry keys and values. Identifies persistence mechanisms (Run/RunOnce), recently accessed files, and USB device history.

**Browser History** — visited URLs, downloads, bookmarks, and cookies with timestamps. Useful for establishing user activity timelines.

**Event Logs** — Windows event log entries (Security, System, Application). Highlights logon events, privilege escalation, service installations, and audit policy changes.

### 5.5 Memory Artefacts

**Processes** — running process list with PIDs, parent PIDs, command lines, and loaded modules. Identifies suspicious process trees, hidden processes, and unusual parent-child relationships.

**Network Connections** — active and recent network connections with local/remote addresses and ports. Highlights connections to known-bad IPs or unusual outbound traffic.

**Injected Code** — code injection indicators including DLL injection, process hollowing, and reflective loading. High-severity artefacts that often indicate malware.

### 5.6 Timeline Analysis

The **Timeline** page presents all artefacts chronologically:

- Interactive timeline visualisation
- Zoom and pan controls
- Colour-coded by suspicion level
- Click any event to view full artefact details

Useful for establishing sequences of events during incident response.

### 5.7 IOC Dashboard

The **IOC Dashboard** provides a focused view of indicators of compromise:

- Summary counts by IOC type (IP, domain, hash, file path, registry key)
- IOC severity distribution
- Cross-reference with artefact sources
- Export IOC list for threat intelligence platforms

---

## Chapter 6 — AI-Assisted Analysis

### 6.1 Running AI Classification

1. Navigate to **AI Analysis**.
2. Select artefacts to classify (or classify all from a case).
3. Click **Run Classification**.

The local LLaMA-3 model analyses each artefact and assigns:
- **Classification** — malicious, suspicious, benign, unknown
- **Confidence Score** — 0.0 to 1.0
- **Reasoning** — brief explanation of the classification

### 6.2 Understanding AI Confidence Scores

| Confidence | Interpretation |
|-----------|---------------|
| 0.8–1.0 | High confidence — model is very certain |
| 0.6–0.79 | Moderate confidence — likely correct but verify |
| 0.4–0.59 | Low confidence — treat as uncertain |
| < 0.4 | Very low — model is uncertain, rely on manual analysis |

### 6.3 Reading the Investigative Summary

The **AI Summary Viewer** presents a narrative summary of the investigation findings, including:

- Key findings and suspicious patterns
- Timeline of significant events
- Recommended next steps

> **Important Disclaimer**: AI-generated analysis is provided as an assistive tool only. All AI outputs must be verified by a qualified forensic examiner before being used in legal proceedings. AI models may hallucinate, miss context, or misinterpret artefacts. See Sharma et al. (2025) for limitations of LLMs in digital forensics.

### 6.4 Using the Investigator Q&A Feature

The Q&A feature allows you to ask natural-language questions about the case:

1. Navigate to **AI Analysis > Q&A**.
2. Type a question (e.g., "What suspicious network connections were found?").
3. The AI responds with relevant artefact references.

This feature uses retrieval-augmented generation (RAG) to ground responses in actual case data.

### 6.5 Understanding AI Limitations

DFAT uses a local LLaMA-3 8B model via Ollama. Limitations include:

- **Hallucination risk** — the model may generate plausible but incorrect analysis
- **Context window** — large cases may exceed the model's context capacity
- **No internet access** — the model has no access to threat intelligence feeds
- **Bias** — model training data may not cover all forensic scenarios
- **Graceful degradation** — if Ollama is unavailable, DFAT falls back to rule-based analysis only

All AI outputs are clearly labelled and include confidence scores.

---

## Chapter 7 — Reports

### 7.1 Viewing Forensic Reports

After a pipeline completes, navigate to **Reports** to view generated reports. Each report contains:

- **JSON View** — structured, schema-validated data
- **Narrative View** — human-readable investigative narrative

### 7.2 Dual-Output Format

DFAT generates two complementary report formats:

**Structured JSON Report**
- Schema-validated against the DFAT report schema
- Machine-readable for integration with other tools
- Contains all artefact data, scores, and classifications
- Includes integrity hash for tamper detection

**Narrative Report**
- Written in plain English for court presentation
- Summarises key findings and evidence
- Includes AI disclaimers where applicable
- Suitable for non-technical stakeholders

### 7.3 Exporting Reports

Reports can be exported in three formats:

- **PDF** — formatted for printing and court submission
- **HTML** — styled report viewable in any browser
- **JSON File** — raw data export with integrity hash

Click the export button on the Report Detail page and select the format.

### 7.4 Verifying Report Integrity

1. Open the report detail page.
2. Click **Verify Integrity**.
3. DFAT recomputes the report hash and compares it to the stored value.
4. Result shows **VERIFIED** or **TAMPERED**.

This ensures reports have not been modified after generation.

### 7.5 Comparing Reports for Reproducibility

1. Navigate to **Reports > Compare**.
2. Select two reports from the same evidence.
3. DFAT compares structural content and highlights differences.

This supports the forensic principle of reproducibility — independent analysis should produce consistent results.

### 7.6 Chain-of-Custody Reports

View the evidence custody chain associated with a report, showing the complete handling history from acquisition through analysis.

### 7.7 Audit Trail Reports

View the complete audit trail for a report, showing every system action that contributed to its generation.

---

## Chapter 8 — Benchmark Evaluation

### 8.1 Running DFRWS/CFReDS Benchmark Evaluations

1. Navigate to **Evaluation > Run Benchmark**.
2. Select a **dataset** (DFRWS or CFReDS).
3. Select the artefacts to evaluate.
4. Click **Run Evaluation**.

The system compares DFAT's findings against ground truth and computes accuracy metrics.

### 8.2 Interpreting Results

| Metric | Definition | Target |
|--------|-----------|--------|
| **Precision** | Proportion of reported artefacts that are correct | > 70% |
| **Recall** | Proportion of ground-truth artefacts that were found | > 70% |
| **F1 Score** | Harmonic mean of precision and recall | > 70% |

Results are displayed on the **Benchmark Results** page with per-category breakdowns.

### 8.3 Time-to-Triage Analysis

The **Performance Dashboard** shows:

- Total pipeline execution time
- Per-stage timing breakdown
- Comparison against previous runs
- Throughput metrics (artefacts per second)

### 8.4 Performance Comparison

Compare multiple benchmark runs to track improvements or regressions over time. The comparison view shows metric trends and highlights significant changes.

---

## Chapter 9 — Usability Questionnaire

### 9.1 Accessing the Questionnaire

The usability questionnaire is available at `/questionnaire` and does not require authentication. This allows evaluation participants to provide feedback without a DFAT account.

### 9.2 Completing the Assessment

The questionnaire uses the System Usability Scale (SUS):

1. Read each statement carefully.
2. Rate your agreement on a scale of 1 (Strongly Disagree) to 5 (Strongly Agree).
3. Answer all questions.
4. Click **Submit**.

The questionnaire takes approximately 5–10 minutes to complete.

### 9.3 Understanding Anonymity Protections

- No personal identifying information is collected.
- Responses are stored with a random identifier.
- IP addresses are not logged for questionnaire submissions.
- Responses cannot be traced back to individual participants.
- Data is used solely for academic evaluation of the DFAT tool.

---

## Chapter 10 — Administration

### 10.1 User Management

Admins can manage users via **Settings > User Management**:

- View all registered users
- View user roles and status
- Deactivate user accounts
- Role assignments are managed through the API

### 10.2 Viewing Audit Logs

Navigate to **Admin > Audit Logs** to view:

- All system actions with timestamps
- User who performed each action
- Action type and affected resource
- Filter by date range, user, or action type

Audit logs are immutable and provide a forensic trail of system usage.

### 10.3 System Settings and Health Monitoring

**Health Monitoring** (Admin > Settings):

- System uptime and version
- Database status and table counts
- AI engine connectivity
- Memory usage
- Component health checks

**Monitoring Endpoints**:

- `/api/v1/monitoring/uptime` — public uptime check
- `/api/v1/monitoring/metrics` — runtime metrics (admin only)
- `/api/v1/monitoring/logs` — recent log entries (admin only)
- `/api/v1/health/detailed` — detailed system diagnostics (admin only)

### 10.4 AI Engine Management

- **AI Health** — check Ollama connectivity and model availability
- **AI Stats** — view classification and summarisation statistics
- **Cache Management** — view cache hit rates and clear the response cache
- **Graceful Degradation** — if Ollama is unavailable, DFAT automatically falls back to rule-based analysis

---

## Appendix A — Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `/` | Focus search bar |
| `Esc` | Close dialog/modal |

## Appendix B — Glossary

| Term | Definition |
|------|-----------|
| **Artefact** | A piece of digital evidence extracted from a forensic image |
| **Chain of Custody** | Documented trail of evidence handling |
| **DFRWS** | Digital Forensic Research Workshop — provides benchmark datasets |
| **CFReDS** | Computer Forensic Reference Data Sets — NIST reference datasets |
| **IOC** | Indicator of Compromise — observable sign of malicious activity |
| **LLaMA-3** | Meta's Large Language Model, used locally via Ollama |
| **Ollama** | Local LLM inference engine |
| **Pipeline** | Automated multi-stage forensic analysis workflow |
| **SUS** | System Usability Scale — standardised usability questionnaire |
| **Triage** | Prioritisation of artefacts by suspicion level |

## Appendix C — Support

For issues or questions:

- Check the **Help** page within DFAT
- Review the [API Examples](../api/EXAMPLES.md)
- Consult the [Operations Guide](../operations/OPERATIONS_GUIDE.md)
- Contact: 100176885@canterbury.ac.uk
