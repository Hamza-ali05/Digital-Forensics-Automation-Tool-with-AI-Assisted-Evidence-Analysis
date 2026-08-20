# ML Lifecycle Architecture

## Overview

The ML extension supports local training, versioning, inference, and optional
auto-retrain for forensic artefact scoring models.

## Components

| Component | Responsibility |
|-----------|----------------|
| `ForensicFeatureExtractor` | Artefact → numeric feature dict |
| `MLDatasetBuilder` | Registry datasets → labelled matrices |
| `ModelTrainer` | sklearn training + experiment logging |
| `ExperimentTracker` | Run metadata on disk |
| `ModelRegistry` | Versioned model index + joblib paths |
| `MLPredictor` | Runtime inference |
| `AutoRetrainer` | Hash-drift triggered retraining |

## Model Wrappers

- `MalwareClassifier`
- `AnomalyDetector`
- `ProcessSuspicionScorer`
- `IOCPredictor`

## Persistence

Alembic migration `008_ml_experiments` adds `ml_experiments` and `ml_model_records`
tables for ORM-backed metadata alongside filesystem artefacts.

## API Surface

- `GET /api/v1/ml/models`
- `GET /api/v1/ml/models/{name}/latest`
- `POST /api/v1/ml/train` (admin)
- `POST /api/v1/ml/retrain` (admin)
- `GET /api/v1/ml/experiments`
- `POST /api/v1/ml/predict`

## Pipeline Integration

`ScoringEngine` accepts an optional `MLPredictor`. ML scores augment — not
replace — rule-based triage (ADR-027).

## Related ADRs

- [ADR-027](adr/027-ml-augments-not-replaces.md)
