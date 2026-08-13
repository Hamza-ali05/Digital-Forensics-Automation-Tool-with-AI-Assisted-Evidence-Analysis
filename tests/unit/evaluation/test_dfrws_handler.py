"""Unit tests for DFRWS ground truth handler (Prompt 6.11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dfat.core.enums import ArtefactCategory
from dfat.core.exceptions import GroundTruthNotFoundError
from dfat.evaluation.benchmark.dfrws_handler import (
    DFRWSHandler,
    GroundTruth,
    GroundTruthArtefact,
)


def _write_dataset(path: Path, name: str = "dfrws_sample") -> Path:
    payload = {
        "dataset_name": name,
        "source": "dfrws",
        "artefacts": [
            {
                "category": "filesystem_metadata",
                "identifier": "legacy-id",
                "expected_data": {
                    "path": "C:\\Windows\\System32\\evil.dll",
                    "filename": "evil.dll",
                },
                "description": "Malicious DLL",
            },
            {
                "category": "registry_key",
                "identifier": "legacy-reg",
                "expected_data": {
                    "hive": "HKCU",
                    "key_path": "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                    "value_name": "Malware",
                },
            },
            {
                "category": "browser_history",
                "identifier": "legacy-url",
                "expected_data": {"url": "http://Malicious.Example/Payload"},
            },
            {
                "category": "event_log",
                "identifier": "legacy-evt",
                "expected_data": {
                    "event_id": "4688",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            },
            {
                "category": "running_process",
                "identifier": "legacy-proc",
                "expected_data": {"name": "mimikatz.exe", "pid": 1337},
            },
            {
                "category": "network_connection",
                "identifier": "legacy-net",
                "expected_data": {
                    "remote_address": "10.0.0.5",
                    "remote_port": 443,
                },
            },
            {
                "category": "injected_code",
                "identifier": "legacy-inj",
                "expected_data": {"pid": 4242, "vad_start": "0x7ffe0000"},
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_list_available_datasets_scans_preplaced_files(tmp_path: Path) -> None:
    """Verify list_available_datasets finds local DFRWS JSON files only."""
    dfrws_dir = tmp_path / "dfrws"
    dfrws_dir.mkdir()
    _write_dataset(dfrws_dir / "challenge_2018.json", name="challenge_2018")
    _write_dataset(tmp_path / "root_dataset.json", name="root_dataset")
    # Non-DFRWS source should be ignored.
    (tmp_path / "cfreds_set.json").write_text(
        json.dumps(
            {
                "dataset_name": "cfreds_set",
                "source": "cfreds",
                "artefacts": [],
            }
        ),
        encoding="utf-8",
    )

    names = DFRWSHandler(tmp_path).list_available_datasets()
    assert "challenge_2018" in names
    assert "root_dataset" in names
    assert "cfreds_set" not in names


def test_load_ground_truth_parses_and_normalises(tmp_path: Path) -> None:
    """Verify load_ground_truth returns typed GroundTruth with normalised IDs."""
    _write_dataset(tmp_path / "dfrws_sample.json")
    handler = DFRWSHandler(tmp_path)
    truth = handler.load_ground_truth("dfrws_sample")

    assert isinstance(truth, GroundTruth)
    assert truth.dataset_name == "dfrws_sample"
    assert truth.source == "DFRWS"
    assert truth.total_count == 7
    assert ArtefactCategory.INJECTED_CODE in truth.categories
    assert all(isinstance(item, GroundTruthArtefact) for item in truth.artefacts)

    by_cat = {item.category: item.identifier for item in truth.artefacts}
    assert by_cat[ArtefactCategory.FILESYSTEM_METADATA].startswith(
        "filesystem_metadata::"
    )
    assert "evil.dll" in by_cat[ArtefactCategory.FILESYSTEM_METADATA]
    assert "c:/windows/system32/evil.dll" in by_cat[ArtefactCategory.FILESYSTEM_METADATA]
    assert "hkcu" in by_cat[ArtefactCategory.REGISTRY_KEY]
    assert "malware" in by_cat[ArtefactCategory.REGISTRY_KEY]
    assert by_cat[ArtefactCategory.BROWSER_HISTORY].endswith(
        "http://malicious.example/payload"
    )
    assert "4688" in by_cat[ArtefactCategory.EVENT_LOG]
    assert "mimikatz.exe" in by_cat[ArtefactCategory.RUNNING_PROCESS]
    assert "1337" in by_cat[ArtefactCategory.RUNNING_PROCESS]
    assert "10.0.0.5" in by_cat[ArtefactCategory.NETWORK_CONNECTION]
    assert "443" in by_cat[ArtefactCategory.NETWORK_CONNECTION]
    assert "4242" in by_cat[ArtefactCategory.INJECTED_CODE]
    assert "0x7ffe0000" in by_cat[ArtefactCategory.INJECTED_CODE]


def test_normalise_identifier_is_consistent() -> None:
    """Verify repeated normalisation yields identical identifiers."""
    handler = DFRWSHandler(Path("."))
    raw = {
        "path": "C:\\Temp\\Payload.EXE",
        "filename": "Payload.EXE",
    }
    first = handler._normalise_identifier("filesystem_metadata", raw)
    second = handler._normalise_identifier("filesystem_metadata", raw)
    assert first == second
    assert first == "filesystem_metadata::c:/temp/payload.exe::payload.exe"


def test_missing_dataset_raises_ground_truth_not_found(tmp_path: Path) -> None:
    """Verify missing datasets raise GroundTruthNotFoundError."""
    handler = DFRWSHandler(tmp_path)
    with pytest.raises(GroundTruthNotFoundError) as exc_info:
        handler.load_ground_truth("does_not_exist")
    assert "does_not_exist" in str(exc_info.value)
