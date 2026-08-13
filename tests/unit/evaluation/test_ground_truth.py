"""Unit tests for ground-truth fixtures and loaders (Prompt 6.20)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dfat.core.exceptions import GroundTruthNotFoundError
from dfat.evaluation.benchmark.cfreds_handler import CFReDSHandler
from dfat.evaluation.benchmark.dfrws_handler import DFRWSHandler, GroundTruth
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader


def _loader(root: Path) -> GroundTruthLoader:
    return GroundTruthLoader(root, DFRWSHandler(root), CFReDSHandler(root))


def test_load_dfrws_format(fixtures_dir: Path, sample_ground_truth: GroundTruth) -> None:
    """Verify DFRWS sample fixture loads with 10 artefacts."""
    path = fixtures_dir / "ground_truth" / "dfrws_sample.json"
    loaded = _loader(path.parent).load(path)
    assert isinstance(loaded, GroundTruth)
    assert loaded.total_count == 10
    assert sample_ground_truth.total_count == 10
    assert loaded.source.upper() == "DFRWS"
    assert loaded.dataset_name == "dfrws_sample"


def test_load_cfreds_format(fixtures_dir: Path) -> None:
    """Verify CFReDS sample fixture loads with 10 artefacts."""
    path = fixtures_dir / "ground_truth" / "cfreds_sample.json"
    loaded = _loader(path.parent).load(path)
    assert isinstance(loaded, GroundTruth)
    assert loaded.total_count == 10
    assert loaded.source.upper() == "CFREDS"
    assert loaded.dataset_name == "cfreds_sample"


def test_missing_dataset_raises_error(tmp_path: Path) -> None:
    """Verify missing ground-truth datasets raise GroundTruthNotFoundError."""
    loader = _loader(tmp_path)
    with pytest.raises(GroundTruthNotFoundError):
        loader.load(tmp_path / "missing.json")
    with pytest.raises(GroundTruthNotFoundError):
        loader.load_dfrws("does_not_exist")


def test_list_available_datasets(fixtures_dir: Path, tmp_path: Path) -> None:
    """Verify list_all_datasets discovers pre-placed DFRWS and CFReDS files."""
    dfrws_dir = tmp_path / "dfrws"
    cfreds_dir = tmp_path / "cfreds"
    dfrws_dir.mkdir()
    cfreds_dir.mkdir()
    shutil.copy(
        fixtures_dir / "ground_truth" / "dfrws_sample.json",
        dfrws_dir / "dfrws_sample.json",
    )
    shutil.copy(
        fixtures_dir / "ground_truth" / "cfreds_sample.json",
        cfreds_dir / "cfreds_sample.json",
    )
    listed = _loader(tmp_path).list_all_datasets()
    assert "dfrws_sample" in listed["dfrws"]
    assert "cfreds_sample" in listed["cfreds"]
