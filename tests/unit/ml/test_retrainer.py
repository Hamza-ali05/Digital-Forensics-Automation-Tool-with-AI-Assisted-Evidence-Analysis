"""Unit tests for AutoRetrainer threshold and audit behaviour."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ml.config import MLSettings
from dfat.ml.retrainer import AutoRetrainer, _dataset_change_ratio
from dfat.ml.trainer import TrainedModel


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ({"a", "b"}, {"a", "b"}, 0.0),
        ({"a", "b"}, {"c", "d"}, 1.0),
        ({"a", "b", "c"}, {"a", "b", "d"}, pytest.approx(0.5)),
        (set(), {"a"}, 1.0),
    ],
)
def test_dataset_change_ratio(previous: set[str], current: set[str], expected: float) -> None:
    assert _dataset_change_ratio(previous, current) == expected


@pytest.mark.asyncio
async def test_check_and_retrain_skips_below_threshold(tmp_path: Path) -> None:
    dataset_registry = MagicMock()
    dataset_registry.list_datasets = AsyncMock(return_value=[MagicMock(hash_sha256="same-hash")])

    model_registry = MagicMock()
    model_registry.get_latest.return_value = TrainedModel(
        model_name="MalwareClassifier",
        model_path=tmp_path / "model.joblib",
        version="1",
        training_dataset="MalwareClassifier",
        metrics={"f1": 0.9, "dataset_hashes": ["same-hash"]},
    )
    model_registry.register = MagicMock()

    retrainer = AutoRetrainer(
        dataset_registry=dataset_registry,
        dataset_builder=MagicMock(),
        trainer=MagicMock(),
        model_registry=model_registry,
        ml_settings=MLSettings(auto_retrain=True, retrain_threshold=0.1),
        audit_service=MagicMock(log_action=AsyncMock()),
    )

    retrained = await retrainer.check_and_retrain()
    assert retrained == []
    model_registry.register.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_retrain_disabled_returns_empty() -> None:
    retrainer = AutoRetrainer(
        dataset_registry=MagicMock(),
        dataset_builder=MagicMock(),
        trainer=MagicMock(),
        model_registry=MagicMock(),
        ml_settings=MLSettings(auto_retrain=False),
        audit_service=MagicMock(),
    )
    assert await retrainer.check_and_retrain() == []
