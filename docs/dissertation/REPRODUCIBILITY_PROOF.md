# Reproducibility Proof

This document explains how DFAT supports reproducible forensic processing and benchmark evaluation.

## 1. Deterministic JSON Output

The primary reproducibility guarantee is the structured JSON report layer in `src/dfat/reporting/json_layer.py`.

Mechanisms:
- artefacts are serialised into a stable dictionary structure
- artefacts are sorted deterministically by `(category, artefact_id)`
- the integrity hash is computed over canonical JSON of the `artefacts` array only
- volatile metadata such as `report_id` and `generated_at` is excluded from the evidential hash

Academic implication:
- identical recovered artefact content yields identical evidential hashes across runs, even if report metadata differs

Verified by:
- `reports/feature_verification.json` (`Feature 1`)

## 2. Schema Versioning

DFAT embeds schema versioning into report output through:
- `src/dfat/shared/constants.py`
- `JSON_SCHEMA_VERSION = "1.0.0"`

The JSON exporter writes this version into:
- top-level `schema_version`
- `reproducibility.schema_version`

This ensures that dissertation evaluation results can always be interpreted against the schema version used at the time of generation.

## 3. Prompt Versioning

AI-related reproducibility is strengthened through:
- `src/dfat/ai_engine/llm/config.py`
- `PROMPT_VERSION = "1.0.0"`

Prompt version is propagated into output via:
- `StructuredJSONExporter._normalise_ai_metadata()`
- `NarrativeAssembler.assemble()`
- prompt template management in `src/dfat/ai_engine/llm/prompts.py`

This matters because prompt changes alter research conditions even if source code otherwise appears unchanged.

## 4. Low Temperature for Stability

The default LLM configuration uses:
- `temperature = 0.1`

This does not make generation fully deterministic, but it reduces stochastic variation and supports more stable outputs between repeated runs.

## 5. Cached Responses for Identical Inputs

The AI stack includes response caching:
- configuration in `src/dfat/container.py`
- cache implementation in `src/dfat/ai_engine/caching/response_cache.py`

Purpose:
- repeated identical requests can reuse prior outputs
- variance is reduced for repeated research demonstrations
- local execution becomes more stable and efficient

## 6. Reproducibility Verifier

DFAT includes explicit reproducibility support in:
- `src/dfat/reporting/reproducibility.py`

This component exists to compare multiple outputs from equivalent runs and determine whether the resulting reports remain consistent enough for research and evidential discussion.

The broader report comparison path is exposed through:
- `src/dfat/api/routes/reports.py`

## 7. Deterministic Ground Truth Comparison

Benchmark evaluation is deterministic because:
- identifiers are normalised before comparison
- TP/FP/FN are computed with set operations
- metric formulas are pure functions
- zero-denominator cases are handled explicitly

Implementation:
- `src/dfat/evaluation/benchmark/comparator.py`
- `src/dfat/evaluation/benchmark/metrics.py`

Verified by:
- `reports/research_objectives_verification.json` (`RQ4`)

## 8. Local-Only Model Constraint

Reproducibility is also helped by restricting AI execution to local endpoints only:
- `src/dfat/ai_engine/llm/connection.py`

This avoids hidden variability from external hosted APIs, remote model changes, and provider-side prompt rewriting.

## 9. Practical Reproduction Procedure

To reproduce a benchmark evaluation run:

1. Use the same code revision.
2. Confirm the same report schema version (`1.0.0`).
3. Confirm the same prompt version (`1.0.0`).
4. Confirm the same Ollama model name and low-temperature configuration.
5. Use the same benchmark dataset file.
6. Use the same evidence input and case metadata.
7. Run the same pipeline stages.
8. Compare:
   - recovered artefact counts
   - benchmark metrics
   - JSON evidential hash
   - report comparison output

## 10. Example Reproduction Workflow

```bash
# 1. Run the backend
python -m uvicorn dfat.app:create_app --factory --reload

# 2. Submit a pipeline job against the same evidence/case
curl -X POST http://localhost:8000/api/v1/pipeline \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"evidence_id": 1, "case_id": 1, "stages": ["acquisition", "parsing", "triage", "reporting", "evaluation"]}'

# 3. Retrieve the generated structured report
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/reports/<report_id>/json

# 4. Compare two reports for reproducibility
curl -X POST http://localhost:8000/api/v1/reports/compare \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"report_id_a": "<report-a>", "report_id_b": "<report-b>"}'
```

## 11. Boundaries of the Claim

DFAT supports **practical reproducibility**, not absolute mathematical determinism.

Residual non-determinism may remain because:
- LLMs are probabilistic systems
- operating-system timing and scheduling vary
- parser-level dependencies may evolve

However, the combination of deterministic JSON ordering, schema versioning, prompt versioning, local-only inference, and benchmark set comparison provides a strong and defensible reproducibility argument for dissertation purposes.
