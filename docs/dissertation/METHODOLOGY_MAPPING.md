# Methodology Mapping

This document maps the dissertation structure to concrete DFAT implementation artefacts, verification scripts, and architectural decisions.

## Chapter 1 — Introduction

### Problem Statement
- The fragmentation problem is addressed in the architectural decision record set under `docs/architecture/adr/`, especially the early design-phase ADRs that justify a unified DFAT platform rather than a chain of disconnected forensic tools.
- The implementation response to that problem is the single application boundary created around the FastAPI backend, React frontend, and five-stage forensic pipeline in `src/dfat/app.py`, `src/dfat/container.py`, and `src/dfat/pipeline/`.

### Research Gap
- The dissertation claim that there is no unified AI-assisted forensic triage tool is implemented as:
  - a single parser/orchestration layer in `src/dfat/forensic_engine/`
  - a local-only LLM analysis layer in `src/dfat/ai_engine/`
  - a dual-output reporting layer in `src/dfat/reporting/`
  - benchmark and usability evaluation in `src/dfat/evaluation/`

## Chapter 2 — Literature Review

### Tool Fragmentation and Pipeline Unification
- The literature-review gap around fragmented forensic workflows is answered by the unified seven-category parser architecture:
  - `src/dfat/pipeline/parser_registry.py`
  - `src/dfat/forensic_engine/orchestrator.py`
  - `src/dfat/forensic_engine/parsers/`
- The verification script `scripts/verify_research_objectives.py` confirms:
  - 8 registered parsers
  - full coverage of all 7 `ArtefactCategory` values
  - routing support for both `DISK_IMAGE` and `MEMORY_DUMP`

### Scanlon et al.
- Scanlon et al.'s concerns about evidential integrity and narrative overreach are addressed by:
  - `src/dfat/ai_engine/validation/hallucination_guard.py`
  - `src/dfat/reporting/json_layer.py`
  - `src/dfat/reporting/narrative.py`
- The JSON layer is explicitly treated as the primary evidential record, while narrative output is supplementary and disclaimer-wrapped.

### Sharma et al. (2025)
- Sharma et al.'s limitations around base LLM suitability for forensic tasks are acknowledged in:
  - `src/dfat/ai_engine/llm/config.py`
  - `src/dfat/ai_engine/llm/prompts.py`
- The mitigation implemented in this dissertation is:
  - local deployment only
  - prompt constraints
  - hallucination detection
  - rule-based fallback
- The future-work path is explicit fine-tuning or replacement with a forensic-domain model.

### Tobin et al.
- Tobin et al.'s usefulness comparison is addressed by:
  - `src/dfat/evaluation/usability/questionnaire.py`
  - `src/dfat/evaluation/usability/response_analyzer.py`
  - `src/dfat/evaluation/usability/tobin_comparison.py`
- `TobinComparison.TOBIN_USEFULNESS_PERCENTAGE` is fixed at `74.0`, enabling direct comparative reporting.

## Chapter 3 — Methodology

### Design Science Research Cycle
- Verified formally by `scripts/verify_dsr_methodology.py` with output in `reports/dsr_verification.json`.
- Mapping:
  - Design: Prompts 1–3
  - Build: Prompts 4–8
  - Evaluate: Prompt 6 and Prompt 10.7 verification layer

### Mixed Methods Design
- Quantitative evaluation:
  - benchmark comparison and metrics in `src/dfat/evaluation/benchmark/`
  - time-to-triage analysis in `src/dfat/evaluation/benchmark/performance.py`
- Qualitative and perception-based evaluation:
  - questionnaire instrument in `src/dfat/evaluation/usability/questionnaire.py`
  - response analysis in `src/dfat/evaluation/usability/response_analyzer.py`

### Toolchain
- Python 3.11: backend and verification scripts
- `pytsk3`, `python-registry`, `Evtx`: disk and registry/event-log parsing assumptions reflected in parser availability logic
- Volatility3: memory analysis path
- LLaMA-3 via Ollama: local AI subsystem

## Chapter 4 — Implementation

### Architecture
- The layered architecture is documented in `docs/architecture/ARCHITECTURE.md`.
- Core implementation anchors:
  - presentation layer: `frontend/src/`
  - API/application layer: `src/dfat/api/`, `src/dfat/services/`
  - domain layer: `src/dfat/core/`
  - infrastructure layer: `src/dfat/database/`, `src/dfat/infrastructure/`

### Five-Stage Pipeline
- Stage implementation:
  - acquisition: `src/dfat/pipeline/stages/acquisition_stage.py`
  - parsing: `src/dfat/pipeline/stages/parsing_stage.py`
  - triage: `src/dfat/pipeline/stages/triage_stage.py`
  - reporting: `src/dfat/pipeline/stages/reporting_stage.py`
  - evaluation: `src/dfat/pipeline/stages/evaluation_stage.py`

### Prompt-to-Code Mapping
- Prompts 1–3: architecture, DI container, interfaces, ADRs
- Prompt 4: unified parser/orchestrator subsystem
- Prompt 5: AI local-only design, fallback, hallucination mitigation
- Prompt 6: reporting, reproducibility, benchmark and usability evaluation
- Prompts 7–8: API and UI pages/workflows
- Prompts 9–10: production readiness, CI/CD, verification, dissertation support docs

## Chapter 5 — Evaluation

### RQ1–RQ5 Result Sources
- Formal verification source: `reports/research_objectives_verification.json`
- Summary:
  - RQ1 passed 5/5 checks
  - RQ2 passed 8/8 checks
  - RQ3 passed 5/5 checks
  - RQ4 passed 5/5 checks
  - RQ5 passed 7/7 checks

### Benchmark Result Sources
- Primary implementation:
  - `src/dfat/evaluation/benchmark/comparator.py`
  - `src/dfat/evaluation/benchmark/metrics.py`
  - `src/dfat/evaluation/benchmark/performance.py`
- Output path:
  - benchmark API routes in `src/dfat/api/routes/evaluation.py`
  - frontend evaluation dashboards in `frontend/src/pages/evaluation/`

### Usability Result Sources
- Data collection:
  - `src/dfat/evaluation/usability/response_collector.py`
- Analysis:
  - `src/dfat/evaluation/usability/response_analyzer.py`
- Comparative benchmark:
  - `src/dfat/evaluation/usability/tobin_comparison.py`

## Chapter 6 — Conclusion

### Limitations
- Base LLaMA-3 rather than a forensic fine-tuned model
- Public benchmark datasets rather than live operational evidence
- Simulated questionnaire participants rather than full practitioner sampling
- MSc project scope and timeframe constraints

### Future Work
- Broader network artefact analysis
- ForensicLLM or equivalent fine-tuning path
- Real-case deployment and practitioner validation
- Distributed or multi-node deployment options

## Direct Citation Support

The most direct dissertation-support artefacts are:
- `reports/research_objectives_verification.json`
- `reports/feature_verification.json`
- `reports/dsr_verification.json`
- `docs/dissertation/EVALUATION_METHODOLOGY.md`
- `docs/dissertation/REPRODUCIBILITY_PROOF.md`
- `docs/dissertation/LIMITATIONS.md`
