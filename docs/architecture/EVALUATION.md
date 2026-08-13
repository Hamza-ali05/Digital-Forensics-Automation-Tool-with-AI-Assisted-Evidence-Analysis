# DFAT Evaluation Architecture

Benchmark methodology, metrics, ground truth, usability questionnaire, and
Tobin et al. comparison for research validation.

Related:

- ADRs: [023](adr/023-questionnaire-immutability.md)–[024](adr/024-tobin-comparability.md)
- Reporting: [`REPORTING.md`](REPORTING.md)

## Benchmark methodology

1. Load local-only DFRWS or CFReDS ground truth (`GroundTruthLoader`; never downloads)
2. Recover artefacts from pipeline output (`ArtefactSet`)
3. Normalise identifiers via `DFRWSHandler._normalise_identifier`
4. Compute TP / FP / FN set intersection
5. Derive precision, recall, F1, accuracy, and time-to-triage
6. Persist `BenchmarkResult` and audit `BENCHMARK_EVALUATION_COMPLETED`

Orchestration: `BenchmarkComparator` + optional `PerformanceAnalyzer` /
`MetricsVisualiser`.

## Metrics formulas

| Metric | Formula | Empty denominator |
|--------|---------|-------------------|
| Precision | TP / (TP + FP) | `0.0` |
| Recall | TP / (TP + FN) | `0.0` |
| F1 | 2PR / (P + R) | `0.0` |
| Accuracy | TP / (TP + FP + FN) | `0.0` |
| Time-to-triage | `end − start` (seconds) | raises if `end ≤ start` |

Per-category metrics use the same formulas independently per `ArtefactCategory`.

## Ground truth format

Fixtures: `tests/fixtures/ground_truth/dfrws_sample.json` and
`cfreds_sample.json` (10 artefacts each).

**DFRWS** (shared schema):

```json
{
  "dataset_name": "...",
  "source": "dfrws",
  "artefacts": [
    {"category": "running_process", "identifier": "...", "expected_data": {}}
  ]
}
```

**CFReDS** (aliases accepted):

- Containers: `items` / `findings` / `expected_artefacts`
- Fields: `name`↔`dataset_name`, `type`↔`category`, `id`↔`identifier`, `data`↔`expected_data`

Handlers search `datasets_dir/` and `datasets_dir/{dfrws|cfreds}/` for pre-placed JSON only.

## Questionnaire instrument

`QuestionnaireInstrument` version `1.0.0` (ethics-locked):

| ID | Type | Role |
|----|------|------|
| Q1–Q5 | Likert 1–5 | Usefulness (Q1,Q4), accuracy (Q2), clarity (Q3), comparative (Q5) |
| Q6 | Open text | Qualitative feedback |

- Participant IDs are anonymised UUIDs
- Invalid ratings raise `ValueError`
- Collection is anonymous via API; analysis/export requires auth

## Tobin et al. comparison

- Benchmark usefulness: **74.0%** (Tobin et al., 2021)
- Tool usefulness % = share of responses with **avg(Q1, Q4) ≥ 4**
- `TobinComparison` emits difference, meets/exceeds flags, and sample-size notes
- Example: 70% tool usefulness → below benchmark (`difference = -4.0`)

Descriptive statistics include mean/median/std-dev and 95% CI (Student’s t for small n).
