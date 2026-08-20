"""Automated retraining when registered training datasets change."""

from __future__ import annotations

import logging
from typing import Any, Optional

from dfat.core.enums import PipelineStage
from dfat.dataset_intelligence.registry import DatasetRegistry
from dfat.ml.config import MLSettings
from dfat.ml.dataset_builder import EmptyTrainingDatasetError, MLDatasetBuilder
from dfat.ml.model_registry import ModelRegistry
from dfat.ml.models import (
    AnomalyDetector,
    IOCPredictor,
    MalwareClassifier,
    ProcessSuspicionScorer,
)
from dfat.ml.trainer import ModelTrainer, TrainedModel, TrainingError
from dfat.services.audit_service import AuditService

logger = logging.getLogger(__name__)

_REGISTERED_MODELS: dict[str, type] = {
    "MalwareClassifier": MalwareClassifier,
    "AnomalyDetector": AnomalyDetector,
    "ProcessSuspicionScorer": ProcessSuspicionScorer,
    "IOCPredictor": IOCPredictor,
}

_PRIMARY_METRIC = "f1"


class AutoRetrainer:
    """Rebuild datasets and retrain models when registry data drifts past threshold."""

    def __init__(
        self,
        dataset_registry: DatasetRegistry,
        dataset_builder: MLDatasetBuilder,
        trainer: ModelTrainer,
        model_registry: ModelRegistry,
        ml_settings: MLSettings,
        audit_service: AuditService,
    ) -> None:
        self._dataset_registry = dataset_registry
        self._dataset_builder = dataset_builder
        self._trainer = trainer
        self._model_registry = model_registry
        self._settings = ml_settings
        self._audit = audit_service

    async def check_and_retrain(self) -> list[str]:
        """Retrain models whose source datasets changed beyond ``retrain_threshold``.

        Returns:
            Names of models that were retrained and registered.
        """
        if not self._settings.auto_retrain:
            return []

        datasets = await self._dataset_registry.list_datasets()
        current_hashes = _dataset_hashes(datasets)
        retrained: list[str] = []

        for model_name, model_class in _REGISTERED_MODELS.items():
            latest = self._model_registry.get_latest(model_name)
            change_ratio = _dataset_change_ratio(
                _stored_dataset_hashes(latest),
                current_hashes,
            )
            if latest is not None and change_ratio <= self._settings.retrain_threshold:
                logger.debug(
                    "Skipping %s retrain; dataset change ratio %.3f <= threshold %.3f",
                    model_name,
                    change_ratio,
                    self._settings.retrain_threshold,
                )
                continue

            try:
                training_data = await self._dataset_builder.build_training_dataset(model_name)
            except EmptyTrainingDatasetError:
                logger.info("No training data available for %s", model_name)
                continue
            except Exception:
                logger.exception("Failed to build training dataset for %s", model_name)
                continue

            try:
                trained = await self._trainer.train(model_class, training_data)
            except TrainingError:
                logger.exception("Training error for %s", model_name)
                continue
            except Exception:
                logger.exception("Unexpected training failure for %s", model_name)
                continue

            trained = _attach_dataset_metadata(trained, current_hashes, change_ratio)
            if not _metrics_improved(latest, trained):
                logger.info(
                    "Skipping registration for %s; metrics did not improve (old=%s new=%s)",
                    model_name,
                    (latest.metrics if latest else {}),
                    trained.metrics,
                )
                continue

            self._model_registry.register(trained)
            retrained.append(model_name)
            await self._audit.log_action(
                stage=PipelineStage.EVALUATION,
                action="MODEL_RETRAINED",
                evidence_id="ml_lifecycle",
                details={
                    "model_name": model_name,
                    "model_id": trained.model_id,
                    "version": trained.version,
                    "dataset_change_ratio": round(change_ratio, 4),
                    "metrics": dict(trained.metrics),
                    "previous_version": latest.version if latest else None,
                },
            )
            logger.info("Retrained and registered %s version %s", model_name, trained.version)

        return retrained


def _dataset_hashes(datasets: list[Any]) -> set[str]:
    return {str(item.hash_sha256) for item in datasets if getattr(item, "hash_sha256", None)}


def _stored_dataset_hashes(model: Optional[TrainedModel]) -> set[str]:
    if model is None:
        return set()
    stored = model.metrics.get("dataset_hashes")
    if isinstance(stored, list):
        return {str(item) for item in stored}
    return set()


def _dataset_change_ratio(previous: set[str], current: set[str]) -> float:
    if not previous and not current:
        return 0.0
    if not previous:
        return 1.0 if current else 0.0
    if not current:
        return 1.0
    union = previous | current
    return min(1.0, len(previous.symmetric_difference(current)) / len(union))


def _attach_dataset_metadata(
    trained: TrainedModel,
    dataset_hashes: set[str],
    change_ratio: float,
) -> TrainedModel:
    metrics = dict(trained.metrics)
    metrics["dataset_hashes"] = sorted(dataset_hashes)
    metrics["dataset_change_ratio"] = round(change_ratio, 4)
    trained.metrics = metrics
    return trained


def _metrics_improved(previous: Optional[TrainedModel], candidate: TrainedModel) -> bool:
    if previous is None:
        return True
    old_score = float(previous.metrics.get(_PRIMARY_METRIC, 0.0))
    new_score = float(candidate.metrics.get(_PRIMARY_METRIC, 0.0))
    return new_score >= old_score
