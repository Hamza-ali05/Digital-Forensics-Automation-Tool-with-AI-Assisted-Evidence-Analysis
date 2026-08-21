"""Bootstrap a minimal trained model when the registry is empty."""

from __future__ import annotations

import logging
from typing import Any, Optional

from dfat.ml.config import MLSettings
from dfat.ml.dataset_builder import TrainingDataset
from dfat.ml.experiment_tracker import ExperimentTracker
from dfat.ml.feature_engineering import ALL_FEATURE_NAMES
from dfat.ml.model_registry import ModelRegistry
from dfat.ml.models import MalwareClassifier
from dfat.ml.trainer import ModelTrainer, TrainingError, TrainedModel

logger = logging.getLogger(__name__)

_BASELINE_MODEL_NAME = "MalwareClassifier"
_BASELINE_SAMPLES = 40


async def ensure_baseline_model(
    registry: ModelRegistry,
    trainer: Optional[ModelTrainer] = None,
    ml_settings: Optional[MLSettings] = None,
) -> Optional[TrainedModel]:
    """Register a synthetic ``MalwareClassifier`` when no models exist.

    Returns:
        The registered ``TrainedModel``, or ``None`` if registration was skipped
        or training failed.
    """
    existing = registry.list_models()
    if existing:
        return existing[0]

    settings = ml_settings or getattr(trainer, "_settings", None) or MLSettings()
    if trainer is None:
        trainer = ModelTrainer(
            experiment_tracker=ExperimentTracker(settings.experiments_dir),
            ml_settings=settings,
        )

    try:
        trained = await trainer.train(
            MalwareClassifier,
            _synthetic_training_dataset(),
            hyperparameters={
                "n_estimators": 25,
                "max_depth": 5,
                "random_state": 42,
                "n_jobs": 1,
            },
        )
        trained.metrics = {
            **dict(trained.metrics),
            "baseline": True,
            "dataset_hashes": [],
        }
        registry.register(trained)
        logger.info(
            "Registered baseline ML model %s@%s",
            trained.model_name,
            trained.version,
        )
        return trained
    except TrainingError as exc:
        logger.warning("Baseline ML training failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Baseline ML bootstrap failed: %s", exc)
        return None


def _synthetic_training_dataset() -> TrainingDataset:
    """Build a tiny balanced feature matrix for first-boot availability."""
    n_features = len(ALL_FEATURE_NAMES)
    matrix: list[list[float]] = []
    labels: list[int] = []
    for index in range(_BASELINE_SAMPLES):
        label = index % 2
        row = [0.0] * n_features
        # Separate classes with a few discriminative features.
        row[0] = float(8 + label * 12 + (index % 5))
        row[1] = float(label * 20 + (index % 3))
        row[2] = float((1 - label) * 15 + (index % 4))
        if n_features > 5:
            row[5] = float(label)
        matrix.append(row)
        labels.append(label)

    train_idx = list(range(0, _BASELINE_SAMPLES - 8))
    val_idx = list(range(_BASELINE_SAMPLES - 8, _BASELINE_SAMPLES - 4))
    test_idx = list(range(_BASELINE_SAMPLES - 4, _BASELINE_SAMPLES))
    return TrainingDataset(
        name=f"{_BASELINE_MODEL_NAME}-baseline",
        feature_matrix=matrix,
        labels=labels,
        feature_names=list(ALL_FEATURE_NAMES),
        train_indices=train_idx,
        val_indices=val_idx,
        test_indices=test_idx,
        class_distribution={
            "benign": _BASELINE_SAMPLES // 2,
            "suspicious": _BASELINE_SAMPLES // 2,
        },
        total_samples=_BASELINE_SAMPLES,
    )
