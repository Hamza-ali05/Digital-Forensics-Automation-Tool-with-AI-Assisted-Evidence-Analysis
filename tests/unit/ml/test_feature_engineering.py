"""Unit tests for forensic feature engineering."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact
from dfat.ml.feature_engineering import (
    ALL_FEATURE_NAMES,
    ForensicFeatureExtractor,
    select_feature_matrix,
)


def _artefact(category: ArtefactCategory, **raw: object) -> Artefact:
    return Artefact(
        artefact_id="art-1",
        category=category,
        source_evidence_id="ev-1",
        raw_data=dict(raw),
        parsed_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def test_process_features_flag_suspicious_name() -> None:
    extractor = ForensicFeatureExtractor()
    features = extractor.extract_process_features(
        _artefact(ArtefactCategory.RUNNING_PROCESS, name="mimikatz.exe", pid=1234)
    )
    assert features["has_suspicious_name"] is True


def test_file_features_detect_high_risk_extension() -> None:
    extractor = ForensicFeatureExtractor()
    features = extractor.extract_file_features(
        _artefact(
            ArtefactCategory.FILESYSTEM_METADATA,
            path=r"C:\Users\Public\payload.ps1",
            size=1024,
        )
    )
    assert features["extension_risk_score"] >= 0.8


def test_network_features_mark_external_ip() -> None:
    extractor = ForensicFeatureExtractor()
    features = extractor.extract_network_features(
        _artefact(
            ArtefactCategory.NETWORK_CONNECTION,
            remote_address="8.8.8.8",
            remote_port=4444,
        )
    )
    assert features["is_external"] is True
    assert features["port_is_suspicious"] is True


def test_select_feature_matrix_builds_named_rows() -> None:
    extractor = ForensicFeatureExtractor()
    rows = [
        extractor.extract_all(_artefact(ArtefactCategory.RUNNING_PROCESS, name="cmd.exe")),
        extractor.extract_all(
            _artefact(ArtefactCategory.FILESYSTEM_METADATA, path="C:\\a.exe")
        ),
    ]
    matrix = select_feature_matrix(rows, ALL_FEATURE_NAMES)
    assert matrix.shape[0] == 2
    assert matrix.shape[1] == len(ALL_FEATURE_NAMES)
