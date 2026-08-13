"""Unit tests for CFReDS handler and generic GroundTruthLoader (Prompt 6.12)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dfat.core.enums import ArtefactCategory
from dfat.core.exceptions import GroundTruthNotFoundError
from dfat.evaluation.benchmark.cfreds_handler import CFReDSHandler
from dfat.evaluation.benchmark.dfrws_handler import DFRWSHandler, GroundTruth
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader


def _write_dfrws(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "dataset_name": "dfrws_auto",
                "source": "dfrws",
                "artefacts": [
                    {
                        "category": "running_process",
                        "identifier": "proc",
                        "expected_data": {"name": "evil.exe", "pid": 1},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_cfreds_alt_format(path: Path) -> None:
    """CFReDS-style document using alternate field names."""
    path.write_text(
        json.dumps(
            {
                "name": "cfreds_hacking",
                "source": "cfreds",
                "findings": [
                    {
                        "type": "browser_history",
                        "id": "bh-1",
                        "data": {"url": "http://CFReDS.Example/Beacon"},
                        "desc": "C2 beacon URL",
                    },
                    {
                        "artefact_type": "network_connection",
                        "key": "net-1",
                        "attributes": {
                            "remote_address": "203.0.113.10",
                            "remote_port": 8080,
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _loader(tmp_path: Path) -> GroundTruthLoader:
    return GroundTruthLoader(
        tmp_path,
        DFRWSHandler(tmp_path),
        CFReDSHandler(tmp_path),
    )


def test_cfreds_handler_loads_alternate_structure(tmp_path: Path) -> None:
    """Verify CFReDSHandler accepts findings/type/data aliases."""
    cfreds_dir = tmp_path / "cfreds"
    cfreds_dir.mkdir()
    _write_cfreds_alt_format(cfreds_dir / "cfreds_hacking.json")

    truth = CFReDSHandler(tmp_path).load_ground_truth("cfreds_hacking")
    assert isinstance(truth, GroundTruth)
    assert truth.dataset_name == "cfreds_hacking"
    assert truth.source == "CFReDS"
    assert truth.total_count == 2
    ids = {item.category: item.identifier for item in truth.artefacts}
    assert ArtefactCategory.BROWSER_HISTORY in ids
    assert "http://cfreds.example/beacon" in ids[ArtefactCategory.BROWSER_HISTORY]
    assert "203.0.113.10" in ids[ArtefactCategory.NETWORK_CONNECTION]
    assert "8080" in ids[ArtefactCategory.NETWORK_CONNECTION]


def test_loader_auto_detects_dfrws_and_cfreds(tmp_path: Path) -> None:
    """Verify GroundTruthLoader.load auto-detects both formats."""
    dfrws_path = tmp_path / "dfrws" / "dfrws_auto.json"
    dfrws_path.parent.mkdir()
    _write_dfrws(dfrws_path)

    cfreds_path = tmp_path / "cfreds" / "cfreds_hacking.json"
    cfreds_path.parent.mkdir()
    _write_cfreds_alt_format(cfreds_path)

    loader = _loader(tmp_path)
    dfrws_truth = loader.load(dfrws_path)
    cfreds_truth = loader.load(cfreds_path)

    assert dfrws_truth.source == "DFRWS"
    assert cfreds_truth.source == "CFReDS"
    assert loader.load_dfrws("dfrws_auto").dataset_name == "dfrws_auto"
    assert loader.load_cfreds("cfreds_hacking").dataset_name == "cfreds_hacking"


def test_list_all_datasets_shows_preplaced_only(tmp_path: Path) -> None:
    """Verify list_all_datasets returns local DFRWS/CFReDS names only."""
    (tmp_path / "dfrws").mkdir()
    (tmp_path / "cfreds").mkdir()
    _write_dfrws(tmp_path / "dfrws" / "dfrws_auto.json")
    _write_cfreds_alt_format(tmp_path / "cfreds" / "cfreds_hacking.json")

    listed = _loader(tmp_path).list_all_datasets()
    assert listed["dfrws"] == ["dfrws_auto"]
    assert listed["cfreds"] == ["cfreds_hacking"]


def test_get_expected_helpers(tmp_path: Path) -> None:
    """Verify artefact count and category helpers on GroundTruth."""
    _write_dfrws(tmp_path / "dfrws_auto.json")
    loader = _loader(tmp_path)
    truth = loader.load_dfrws("dfrws_auto")
    assert loader.get_expected_artefact_count(truth) == 1
    assert ArtefactCategory.RUNNING_PROCESS in loader.get_expected_categories(truth)


def test_missing_cfreds_raises(tmp_path: Path) -> None:
    """Verify missing CFReDS datasets raise GroundTruthNotFoundError."""
    with pytest.raises(GroundTruthNotFoundError):
        CFReDSHandler(tmp_path).load_ground_truth("missing")
