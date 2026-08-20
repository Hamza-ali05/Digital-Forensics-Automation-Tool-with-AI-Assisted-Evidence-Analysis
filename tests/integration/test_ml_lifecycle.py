"""Integration tests for ML lifecycle: build, train, predict, retrain."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("sklearn")

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact
from dfat.ml.config import MLSettings
from dfat.ml.dataset_builder import TrainingDataset
from dfat.ml.experiment_tracker import ExperimentTracker
from dfat.ml.feature_engineering import ALL_FEATURE_NAMES, ForensicFeatureExtractor
from dfat.ml.model_registry import ModelRegistry
from dfat.ml.predictor import MLPredictor
from dfat.ml.retrainer import AutoRetrainer
from dfat.ml.trainer import ModelTrainer


def _artefact(artefact_id: str, name: str) -> Artefact:
    return Artefact(
        artefact_id=artefact_id,
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev-ml",
        raw_data={"name": name, "pid": 100},
    )


def _training_dataset() -> TrainingDataset:
    extractor = ForensicFeatureExtractor()
    rows = [
        [float(extractor.extract_all(_artefact("a1", "mimikatz.exe"))[name]) for name in ALL_FEATURE_NAMES],
        [float(extractor.extract_all(_artefact("a2", "notepad.exe"))[name]) for name in ALL_FEATURE_NAMES],
        [float(extractor.extract_all(_artefact("a3", "cmd.exe"))[name]) for name in ALL_FEATURE_NAMES],
        [float(extractor.extract_all(_artefact("a4", "explorer.exe"))[name]) for name in ALL_FEATURE_NAMES],
    ]
    labels = [1, 0, 1, 0]
    return TrainingDataset(
        name="ProcessSuspicionScorer",
        feature_matrix=rows,
        labels=labels,
        feature_names=list(ALL_FEATURE_NAMES),
        train_indices=[0, 1, 2],
        val_indices=[3],
        test_indices=[3],
        class_distribution={"0": 2, "1": 2},
        total_samples=4,
    )


@pytest.mark.asyncio
async def test_train_and_predict_lifecycle(tmp_path: Path) -> None:
    from dfat.ml.models import MalwareClassifier

    settings = MLSettings(
        models_dir=tmp_path / "models",
        experiments_dir=tmp_path / "experiments",
        random_seed=42,
        cross_validation_folds=2,
    )
    trainer = ModelTrainer(ExperimentTracker(settings.experiments_dir), settings)
    registry = ModelRegistry(settings.models_dir)
    data = _training_dataset()
    data.name = "MalwareClassifier"
    trained = await trainer.train(MalwareClassifier, data)
    registry.register(trained)

    predictor = MLPredictor(registry, ForensicFeatureExtractor())
    prediction = await predictor.predict("MalwareClassifier", _artefact("a5", "mimikatz.exe"))

    assert prediction.artefact_id == "a5"
    assert 0.0 <= prediction.confidence <= 1.0


@pytest.mark.asyncio
async def test_auto_retrainer_skips_when_no_new_datasets(tmp_path: Path) -> None:
    settings = MLSettings(
        models_dir=tmp_path / "models",
        experiments_dir=tmp_path / "experiments",
        auto_retrain=False,
    )
    registry = ModelRegistry(settings.models_dir)
    dataset_registry = AsyncMock()
    dataset_registry.list_datasets = AsyncMock(return_value=[])
    builder = AsyncMock()
    trainer = AsyncMock()
    retrainer = AutoRetrainer(
        dataset_registry=dataset_registry,
        dataset_builder=builder,
        trainer=trainer,
        model_registry=registry,
        ml_settings=settings,
        audit_service=AsyncMock(),
    )

    retrained = await retrainer.check_and_retrain()

    assert retrained == []
    trainer.train.assert_not_awaited()


@pytest.mark.asyncio
async def test_registry_lists_trained_model_versions(tmp_path: Path) -> None:
    from joblib import dump
    from sklearn.tree import DecisionTreeClassifier

    settings = MLSettings(
        models_dir=tmp_path / "models",
        experiments_dir=tmp_path / "experiments",
        random_seed=42,
        cross_validation_folds=2,
    )
    trainer = ModelTrainer(ExperimentTracker(settings.experiments_dir), settings)
    registry = ModelRegistry(settings.models_dir)
    data = _training_dataset()

    first = await trainer.train(DecisionTreeClassifier, data)
    registry.register(first)
    second = await trainer.train(DecisionTreeClassifier, data)
    registry.register(second)

    versions = registry.compare_versions(first.model_name)
    assert len(versions) == 2
    assert registry.get_latest(first.model_name) is not None
