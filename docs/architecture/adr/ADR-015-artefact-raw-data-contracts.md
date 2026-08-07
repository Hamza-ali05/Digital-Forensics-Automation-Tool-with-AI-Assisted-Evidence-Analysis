# ADR-015: Artefact `raw_data` Contracts

## Status
Accepted

## Context
Each `ArtefactCategory` produces a structured `raw_data` dict. Downstream
consumers — AI engine prompts, the evaluation comparator, the JSON report schema,
triage rules, and the frontend — all depend on those fields. Free-form parser
dumps would break scoring, correlation, evaluation, and UI bindings.

## Decision
Each `ArtefactCategory` has a documented `raw_data` schema (the dict structure
produced by parsers). These schemas are **frozen after implementation**.

- Contracts live in parser module docstrings and are summarised in
  [`PIPELINE.md`](../PIPELINE.md).
- Parsers emit only the contracted keys and documented value types.
- AI prompts, evaluation, reports, and triage read contracted fields only.

Categories: `FILESYSTEM_METADATA`, `REGISTRY_KEY`, `BROWSER_HISTORY`,
`EVENT_LOG`, `RUNNING_PROCESS`, `NETWORK_CONNECTION`, `INJECTED_CODE`.

## Consequences
- Schema changes require coordinated updates across parsers, AI prompts,
  evaluation, JSON reports, docs, and frontend types.
- Cross-parser consistency (e.g. disk vs memory `REGISTRY_KEY`) is intentional.
- Invalid or missing keys degrade scoring gracefully but are treated as bugs.
