"""Unit tests for ModelTrainer."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("sklearn")

from dfat.ml.config import MLSettings
from dfat.ml.dataset_builder import TrainingDataset
from dfat.ml.experiment_tracker import ExperimentTracker
from dfat.ml.trainer import ModelTrainer, TrainingError


@pytest.fixture
def trainer(tmp_path: Path) -> ModelTrainer:
    tracker = ExperimentTracker(tmp_path / "experiments")
    settings = MLSettings(
        models_dir=tmp_path / "models",
        experiments_dir=tmp_path / "experiments",
        random_seed=42,
        cross_validation_folds=2,
        max_training_time_seconds=30,
    )
    return ModelTrainer(tracker, settings)


def _training_data() -> TrainingDataset:
    features = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 1.0],
    ]
    labels = [1, 0, 1, 0]
    return TrainingDataset(
        name="TestModel",
        feature_matrix=features,
        labels=labels,
        feature_names=["f1", "f2", "f3", "f4"],
        train_indices=[0, 1, 2],
        val_indices=[3],
        test_indices=[3],
        class_distribution={"0": 2, "1": 2},
        total_samples=4,
    )


@pytest.mark.asyncio
async def test_train_persists_model_and_metrics(trainer: ModelTrainer, tmp_path: Path) -> None:
    from sklearn.tree import DecisionTreeClassifier

    trained = await trainer.train(DecisionTreeClassifier, _training_data())
    assert trained.model_name
    assert trained.model_path.exists()
    assert "accuracy" in trained.metrics or "f1" in trained.metrics


@pytest.mark.asyncio
async def test_train_increments_version(trainer: ModelTrainer) -> None:
    from sklearn.tree import DecisionTreeClassifier

    first = await trainer.train(DecisionTreeClassifier, _training_data())
    second = await trainer.train(DecisionTreeClassifier, _training_data())
    assert int(second.version) > int(first.version)


@pytest.mark.asyncio
async def test_train_rejects_empty_dataset(trainer: ModelTrainer) -> None:
    from sklearn.tree import DecisionTreeClassifier

    empty = TrainingDataset(
        name="Empty",
        feature_matrix=[],
        labels=[],
        feature_names=["f1"],
        train_indices=[],
        val_indices=[],
        test_indices=[],
        class_distribution={},
        total_samples=0,
    )
    with pytest.raises(TrainingError):
        await trainer.train(DecisionTreeClassifier, empty)
