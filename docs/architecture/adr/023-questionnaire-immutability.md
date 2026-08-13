# ADR-023: Questionnaire Instrument Immutability

## Status
Accepted

## Context
Usability evaluation (RQ5) depends on a fixed ethics-approved instrument.
Changing question wording mid-study would invalidate Tobin comparisons and
aggregated statistics.

## Decision
`QuestionnaireInstrument` is ethics-locked at `INSTRUMENT_VERSION = "1.0.0"`
with exactly six questions (Q1–Q5 Likert, Q6 open). Question text and IDs must
not change without a new instrument version, ethics re-approval, and explicit
migration of response analysis code.

## Consequences
- Response collectors persist version metadata with submissions.
- Tests assert six questions and reject out-of-range Likert scores.
- Comparative usefulness uses avg(Q1, Q4) ≥ 4 as defined for Tobin alignment.
