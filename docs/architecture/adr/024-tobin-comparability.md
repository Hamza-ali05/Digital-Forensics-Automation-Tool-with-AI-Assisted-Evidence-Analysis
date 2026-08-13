# ADR-024: Tobin et al. Comparability

## Status
Accepted

## Context
Research question RQ5 requires comparing DFAT usefulness results to published
forensic-tool usability benchmarks. Tobin et al. (2021) report 74% usefulness.

## Decision
`TobinComparison.TOBIN_USEFULNESS_PERCENTAGE = 74.0` is the fixed literature
benchmark. Tool usefulness percentage is the share of anonymised responses with
avg(Q1, Q4) ≥ 4. Results report difference, meets/exceeds flags, and sample-size
caveats when n < 30 or Tobin's n is unspecified.

## Consequences
- 70% tool usefulness correctly classifies as below benchmark.
- Evaluation reports always embed a Tobin comparison block.
- Absolute percentage comparisons are interpreted cautiously without Tobin's n.
