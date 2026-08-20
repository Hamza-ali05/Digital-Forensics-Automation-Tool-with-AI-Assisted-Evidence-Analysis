"""Unit tests for ML inference and score merging."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact
from dfat.ml.feature_engineering import ForensicFeatureExtractor
from dfat.ml.model_registry import ModelRegistry
from dfat.ml.predictor import MLPredictor, prediction_to_score
from dfat.ml.trainer import TrainedModel


def _artefact(artefact_id: str = "a1") -> Artefact:
    return Artefact(
        artefact_id=artefact_id,
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev-1",
        raw_data={"name": "cmd.exe", "pid": 100, "parent_name": "explorer.exe"},
    )


@pytest.mark.asyncio
async def test_predictor_returns_confidence(tmp_path: Path) -> None:
    from joblib import dump
    from sklearn.ensemble import RandomForestClassifier

    from dfat.ml.models import MalwareClassifier

    wrapper = MalwareClassifier()
    feature_names = wrapper.get_feature_names()
    registry = ModelRegistry(tmp_path / "models")
    estimator = RandomForestClassifier(n_estimators=5, random_state=42)
    estimator.fit([[1.0] * len(feature_names), [0.0] * len(feature_names)], [1, 0])
    model_path = tmp_path / "models" / "MalwareClassifier" / "1" / "model.joblib"
    model_path.parent.mkdir(parents=True)
    dump(estimator, model_path)
    trained = TrainedModel(
        model_name="MalwareClassifier",
        model_path=model_path,
        version="1",
        training_dataset="MalwareClassifier",
        feature_names=feature_names,
        metrics={"f1": 0.9},
    )
    registry.register(trained)

    predictor = MLPredictor(registry, ForensicFeatureExtractor())
    result = await predictor.predict("MalwareClassifier", _artefact())

    assert result.artefact_id == "a1"
    assert result.model_name == "MalwareClassifier"
    assert result.model_version == "1"
    assert 0.0 <= result.confidence <= 1.0
    assert result.prediction in {0, 1, True, False}


def test_prediction_to_score_maps_numeric_labels() -> None:
    assert prediction_to_score(1, 0.75) == pytest.approx(0.75)
    assert prediction_to_score(0, 0.75) == pytest.approx(0.25)


def test_prediction_to_score_maps_boolean_labels() -> None:
    assert prediction_to_score(True, 0.8) == pytest.approx(0.8)
    assert prediction_to_score(False, 0.8) == pytest.approx(0.2)
