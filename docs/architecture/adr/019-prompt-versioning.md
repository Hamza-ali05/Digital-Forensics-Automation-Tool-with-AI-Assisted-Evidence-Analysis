# ADR-019: Prompt Versioning for Reproducibility

## Status
Accepted

## Context
LLM triage outputs must be reproducible for evaluation and peer review. Prompt
drift between runs would invalidate benchmark comparisons and audit trails.

## Decision
All forensic prompt templates share a package-level `PROMPT_VERSION` constant
(currently `1.0.0` in `dfat.ai_engine.llm.config` / `llm.prompts`). Summary and
AI analysis records persist `prompt_version` alongside `model_used`, temperature,
and related generation parameters.

Template changes that alter model behaviour require a version bump. Jinja2
templates under the AI engine remain the single source of rendered prompts
(classification, ranking, summary, explanation, Q&A).

## Consequences
- Benchmarks and `AIAnalysisRecordORM` rows can be correlated by prompt version.
- Investigators can reproduce a run given model name + prompt version + inputs.
- Documentation and OpenAPI responses surface version metadata where applicable.
