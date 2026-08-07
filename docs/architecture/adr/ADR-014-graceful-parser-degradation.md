# ADR-014: Graceful Parser Degradation

## Status
Accepted

## Context
A single missing library or corrupt evidence slice must not fail an entire
investigation. Disk and memory parsers are independent; partial artefact recovery
is forensically valuable.

## Decision
Individual parser failures do not abort the pipeline. The orchestrator (via
`PipelineErrorHandler`) catches parser exceptions, logs them, and continues with
remaining parsers. Only if **all** parsers fail (zero artefacts recovered) does
the parsing stage abort the job.

Supporting policy:

- `handle_parser_error()` records `FAILED` / `UNAVAILABLE` without re-raising to
  sibling parsers.
- `assemble_partial_results()` builds a usable `ArtefactSet` from successes.
- Stage abort: acquisition / reporting failures abort; triage and evaluation
  failures do not (`should_abort_pipeline`).

This ensures maximum artefact recovery even with partial library support.

## Consequences
- Jobs can complete with incomplete category coverage; UI and reports must show
  per-parser status in `stage_executions` / progress APIs.
- Investigators get best-effort results in constrained environments.
- Complements ADR-005 (library absence) with runtime pipeline policy.
