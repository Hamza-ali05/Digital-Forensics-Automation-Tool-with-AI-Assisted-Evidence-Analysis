"""Unit tests for ModelRegistry."""

from __future__ import annotations

from pathlib import Path

import pytest
from joblib import dump

from dfat.ml.model_registry import ModelRegistry
from dfat.ml.trainer import TrainedModel


def _trained(tmp_path: Path, *, version: str = "1", model_id: str = "m-1") -> TrainedModel:
    model_path = tmp_path / "models" / "TestModel" / version / "model.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    dump({"estimator": "stub"}, model_path)
    return TrainedModel(
        model_id=model_id,
        model_name="TestModel",
        model_path=model_path,
        version=version,
        training_dataset="ds",
        metrics={"f1": 0.8},
        feature_names=["f1"],
    )


def test_register_and_get_latest(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "registry")
    first = _trained(tmp_path, version="1", model_id="m-1")
    second = _trained(tmp_path, version="2", model_id="m-2")
    registry.register(first)
    registry.register(second)
    latest = registry.get_latest("TestModel")
    assert latest is not None
    assert latest.version == "2"


def test_get_version_returns_specific_record(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "registry")
    model = _trained(tmp_path, version="3", model_id="m-3")
    registry.register(model)
    assert registry.get_version("TestModel", "3") is not None
    assert registry.get_version("TestModel", "99") is None


def test_load_model_reads_joblib_file(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "registry")
    model = _trained(tmp_path, version="1", model_id="m-load")
    registry.register(model)
    loaded = registry.load_model(model.model_id)
    assert loaded == {"estimator": "stub"}
