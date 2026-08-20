# ADR-027: ML Augments — Not Replaces — Rule-Based Triage

## Status
Accepted

## Context
Prompt 11 adds ML models for artefact scoring. ADR-016/020 establish rule-based
triage as the primary, explainable path. ML must improve ranking without
superseding deterministic forensic logic or breaking dissertation RQ baselines.

## Decision
`MLPredictor` produces optional suspicion scores merged in `ScoringEngine` with
weights 0.5 rule / 0.3 baseline / 0.2 ML when ML is available; 0.6 / 0.4 when
not. Auto-retrain runs only when configured thresholds are exceeded. Models are
versioned in a local `ModelRegistry` with experiment tracking.

## Consequences
- Pipeline operates correctly with zero trained models registered.
- ML training, registry, and inference are isolated in `dfat.ml`.
- API routes expose read/inference to analysts; training is admin-only.
- Related: ADR-016, ADR-020.
