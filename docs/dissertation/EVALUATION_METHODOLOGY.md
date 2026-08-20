# Evaluation Methodology

This document describes the academic evaluation methodology implemented in DFAT for dissertation Chapter 5.

## 1. Benchmark Dataset Selection Rationale

DFAT uses public benchmark datasets rather than operational case data. The selected benchmark families are:

- **DFRWS**: appropriate for repeatable academic evaluation of digital forensic artefact extraction and triage.
- **CFReDS**: appropriate for reference-style forensic validation where expected findings are explicitly documented.

These datasets were selected because they:
- allow reproducible comparison
- avoid legal and ethical complications of live case evidence
- provide known or derivable ground truth
- support category-level evaluation across filesystem, registry, browser, event-log, and memory-oriented artefacts

Implementation anchors:
- `src/dfat/evaluation/benchmark/ground_truth.py`
- `src/dfat/evaluation/benchmark/dfrws_handler.py`
- `src/dfat/evaluation/benchmark/cfreds_handler.py`

## 2. Ground Truth Format Specification

Ground truth is loaded through `GroundTruthLoader`, which auto-detects DFRWS versus CFReDS format.

Core expectations:
- a dataset name
- source identifier (`dfrws` or `cfreds`)
- a list of expected artefacts
- artefact categories
- expected identifiers and supporting raw expected data

The loader supports:
- path-based detection from folder structure
- JSON-field-based detection via `source`
- fallback structural detection for ambiguous files

This design is academically important because it prevents evaluation logic from being hard-coded to one benchmark family.

## 3. Metrics Definitions

DFAT uses standard information-retrieval metrics:

- **Precision**: `P = TP / (TP + FP)`
- **Recall**: `R = TP / (TP + FN)`
- **F1 Score**: `F1 = 2PR / (P + R)`
- **Accuracy-style support metric**: `TP / (TP + FP + FN)`

Implementation:
- `src/dfat/evaluation/benchmark/metrics.py`

The implementation explicitly handles division-by-zero cases by returning `0.0` instead of raising an error. This was verified by `scripts/verify_research_objectives.py`.

## 4. Identifier Normalisation Methodology

Recovered artefacts and ground-truth artefacts cannot be compared safely using raw strings alone. DFAT therefore normalises identifiers before TP/FP/FN computation.

Method:
1. Recovered artefacts are transformed into comparison keys through `BenchmarkComparator._artefact_key()`.
2. Ground-truth entries are transformed through `BenchmarkComparator._ground_truth_key()`.
3. Both use DFRWS-normalisation logic to standardise identifiers by category and expected fields.
4. Set operations are then used:
   - `TP = recovered ∩ expected`
   - `FP = recovered − expected`
   - `FN = expected − recovered`

This method reduces false mismatches caused by formatting differences and is central to the validity of RQ4.

## 5. Time-to-Triage Measurement Methodology

Time-to-triage is treated as a quantitative performance outcome supporting RQ3.

Definition:
- `time_to_triage_seconds = pipeline_end - pipeline_start`

Implementation:
- `MetricsCalculator.compute_time_to_triage()`
- `PerformanceAnalyzer.compute_time_statistics()`
- `PerformanceAnalyzer.compare_against_baseline()`

Instrumentation sources:
- `src/dfat/forensic_engine/orchestrator.py`
- `src/dfat/pipeline/job_runner.py`
- `src/dfat/shared/timing.py`

The implementation verifies that timing is:
- positive
- stage-aware in the pipeline/orchestrator code
- statistically summarised across runs using mean, median, p95, and p99

## 6. Usability Questionnaire Design Rationale

Usability evaluation addresses RQ5 through a fixed six-question instrument in:
- `src/dfat/evaluation/usability/questionnaire.py`

Design rationale:
- short enough for practical administration in an MSc context
- mixes structured Likert responses with one qualitative free-text item
- supports usefulness, accuracy, clarity, and comparative perception
- remains frozen after ethics approval to protect methodological consistency

The questionnaire is intentionally public at the route level for participant convenience:
- `/api/v1/evaluation/usability/questionnaire`
- `/api/v1/evaluation/usability/respond`

## 7. Tobin et al. Comparison Methodology

The dissertation compares observed usefulness against a literature benchmark:
- `TobinComparison.TOBIN_USEFULNESS_PERCENTAGE = 74.0`

DFAT computes usefulness as:
- the percentage of respondents whose average usefulness score is at least 4
- implemented in `ResponseAnalyzer.compute_usefulness_percentage()`

This does not claim one-to-one methodological identity with Tobin et al.; instead it provides a justified comparative anchor for discussion.

## 8. Statistical Analysis Methods

Quantitative analysis includes:
- arithmetic mean
- median
- standard deviation
- min/max
- p95 and p99 percentiles for timing distributions
- 95% confidence intervals for questionnaire dimensions

Implementation:
- `src/dfat/evaluation/benchmark/performance.py`
- `src/dfat/evaluation/usability/response_analyzer.py`

Confidence intervals are:
- Student's t for small samples
- normal approximation for larger degrees of freedom

These methods are appropriate for descriptive evaluation in a dissertation where the emphasis is on transparency rather than inferential overclaiming.

## 9. Sample Size Considerations and Limitations

### Benchmark Sample Considerations
- Benchmark validity depends on dataset variety rather than participant count.
- Public datasets improve reproducibility but may not represent full real-world heterogeneity.

### Usability Sample Considerations
- Small participant counts may produce unstable percentages and wider confidence intervals.
- `TobinComparison` explicitly notes caution when tool sample size is below 30.
- Simulated investigators are useful for structured pilot evidence, but they are not equivalent to a large practitioner cohort.

### Interpretive Boundaries
- The evaluation supports an MSc dissertation claim of implemented capability and measured performance.
- It should not be overstated as conclusive operational superiority across all forensic environments.

## 10. Verification Linkage

The methodology described here is reinforced by:
- `reports/research_objectives_verification.json`
- `reports/feature_verification.json`
- `reports/dsr_verification.json`

Most importantly:
- RQ3 verification confirms timing instrumentation and statistics support.
- RQ4 verification confirms benchmark metrics and per-category breakdown.
- RQ5 verification confirms questionnaire versioning, anonymisation, public access, and ethics-driven deletion support.
