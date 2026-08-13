# DFAT Reporting Architecture

Structured dual-output forensic reporting: schema, exporters, integrity, and
reproducibility guarantees.

Related:

- ADRs: [021](adr/021-json-layer-primary-record.md)–[022](adr/022-report-schema-versioning.md), [ADR-003](adr/ADR-003-dual-output-report.md)
- Evaluation: [`EVALUATION.md`](EVALUATION.md)

## Dual-output model

| Layer | Type | Role |
|-------|------|------|
| JSON | `JSONReport` | Primary evidential record (artefacts + integrity hash) |
| Narrative | `NarrativeReport` | Advisory investigative text with Scanlon disclaimer |
| Combined | `ForensicReport` | Case envelope, stage timings, audit metadata |

Assembly is performed by `DualOutputReportBuilder` (`IReportGenerator`).

## Report schema

- Canonical schema: `src/dfat/reporting/schema/report_schema.json`
- Current version: `1.0.0` (`JSON_SCHEMA_VERSION`)
- Validation: `ReportSchemaValidator`
- Artefacts are sorted deterministically by `(category, artefact_id)` before hash

Document shape (simplified):

```text
schema_version, report_id, evidence_id, case_metadata, generated_at,
integrity_hash, pipeline_stage_timings, artefacts[], summary_statistics,
ai_metadata, reproducibility
```

## Export formats

| Format | Module | Notes |
|--------|--------|-------|
| Structured JSON (in-memory) | `StructuredJSONExporter` | Schema-validated; SHA-256 artefact hash |
| JSON file | `JSONFileExporter` | Verifies integrity before write |
| HTML | `HTMLReportExporter` | Self-contained (inline CSS/JS); colour-coded suspicion rows |
| PDF | `PDFReportExporter` | reportlab/weasyprint when available; plaintext `.txt` fallback otherwise |
| Custody / audit | generators under `reporting/generators` | Chain-of-custody and audit trail views |

## Integrity verification

`ReportIntegrityVerifier`:

1. Recomputes SHA-256 over the canonical JSON serialisation of the artefact array
2. Checks `schema_version` against the registry
3. Validates `report_id` as UUID
4. Optionally embeds `audit_metadata` (user, job, host, custody length, tool version)

Tampering with any artefact field fails verification; envelope metadata changes
do not affect the integrity hash.

## Reproducibility guarantees

`ReproducibilityVerifier.compare_reports`:

- Two runs on identical artefact inputs → identical integrity hashes
- Diffs list hash mismatches, missing artefacts, and per-field changes
- `verify_determinism` re-hashes artefacts and compares to the stored hash

Narrative text is **not** part of the reproducibility hash contract.
