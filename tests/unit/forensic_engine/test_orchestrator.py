"""Unit tests for ForensicOrchestrator parser routing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm
from dfat.core.exceptions import UnsupportedFormatError
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.forensic_engine.normalizer import ArtefactNormalizer
from dfat.forensic_engine.orchestrator import ForensicOrchestrator


def _build_orchestrator(
    parsers: list[MagicMock],
    disk_handler: MagicMock,
    memory_handler: MagicMock,
    audit_logger: MagicMock,
) -> ForensicOrchestrator:
    """Helper to construct a ForensicOrchestrator with mocks."""
    integrity = MagicMock()
    integrity.verify_integrity.return_value = True
    return ForensicOrchestrator(
        parsers=parsers,  # type: ignore[arg-type]
        normalizer=ArtefactNormalizer(),
        integrity_checker=integrity,
        disk_handler=disk_handler,
        memory_handler=memory_handler,
        audit_logger=audit_logger,
    )


def _disk_evidence(path: Path, case: CaseMetadata) -> EvidenceImage:
    """Build a disk EvidenceImage fixture."""
    return EvidenceImage(
        evidence_id="ev-disk",
        file_path=path,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=path.stat().st_size,
        case=case,
    )


def test_process_evidence_routes_dd_to_disk_handler(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify .dd evidence is loaded via the disk image handler."""
    # Arrange
    evidence_path = tmp_path / "disk.dd"
    evidence_path.write_bytes(b"disk")
    disk_handler = MagicMock()
    disk_handler.load_image.return_value = _disk_evidence(evidence_path, sample_case_metadata)
    parser = MagicMock()
    parser.parser_name = "MockFS"
    parser.supported_evidence_types.return_value = [EvidenceType.DISK_IMAGE]
    parser.parse.return_value = ArtefactSet(
        evidence_id="ev-disk",
        artefacts=[
            Artefact(
                category=ArtefactCategory.FILESYSTEM_METADATA,
                source_evidence_id="ev-disk",
                raw_data={"path": "/a"},
            )
        ],
        categories_present=[ArtefactCategory.FILESYSTEM_METADATA],
    )
    orchestrator = _build_orchestrator(
        [parser],
        disk_handler,
        MagicMock(),
        mock_audit_logger,
    )

    # Act
    loaded, artefact_set = orchestrator.process_evidence(evidence_path, sample_case_metadata)

    # Assert
    disk_handler.load_image.assert_called_once()
    assert loaded.evidence_id == "ev-disk"
    assert artefact_set.total_count >= 1


def test_process_evidence_skips_failing_parser(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify a failing parser is skipped without aborting the run."""
    # Arrange
    evidence_path = tmp_path / "disk.dd"
    evidence_path.write_bytes(b"disk")
    disk_handler = MagicMock()
    disk_handler.load_image.return_value = _disk_evidence(evidence_path, sample_case_metadata)
    bad_parser = MagicMock()
    bad_parser.parser_name = "Bad"
    bad_parser.supported_evidence_types.return_value = [EvidenceType.DISK_IMAGE]
    bad_parser.parse.side_effect = RuntimeError("parser boom")
    good_parser = MagicMock()
    good_parser.parser_name = "Good"
    good_parser.supported_evidence_types.return_value = [EvidenceType.DISK_IMAGE]
    good_parser.parse.return_value = ArtefactSet(
        evidence_id="ev-disk",
        artefacts=[],
        categories_present=[],
    )
    orchestrator = _build_orchestrator(
        [bad_parser, good_parser],
        disk_handler,
        MagicMock(),
        mock_audit_logger,
    )

    # Act
    _, artefact_set = orchestrator.process_evidence(evidence_path, sample_case_metadata)

    # Assert
    assert artefact_set.evidence_id == "ev-disk"
    good_parser.parse.assert_called_once()


def test_process_evidence_rejects_unsupported_extension(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify unsupported evidence extensions raise UnsupportedFormatError."""
    # Arrange
    evidence_path = tmp_path / "notes.txt"
    evidence_path.write_text("not evidence", encoding="utf-8")
    orchestrator = _build_orchestrator([], MagicMock(), MagicMock(), mock_audit_logger)

    # Act / Assert
    with pytest.raises(UnsupportedFormatError):
        orchestrator.process_evidence(evidence_path, sample_case_metadata)
