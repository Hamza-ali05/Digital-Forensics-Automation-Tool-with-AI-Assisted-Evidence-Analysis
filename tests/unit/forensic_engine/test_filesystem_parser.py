"""Unit tests for FileSystemParser with a mocked DiskImageAccessor."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.disk_access import FileEntry
from dfat.forensic_engine.parsers.filesystem import FileSystemParser


def _entries() -> list[FileEntry]:
    """Synthetic filesystem entries for walk_filesystem."""
    return [
        FileEntry(
            name="hosts",
            path="/Windows/System32/drivers/etc/hosts",
            size=128,
            inode=42,
            file_type="file",
            is_deleted=False,
            is_allocated=True,
            created_time=datetime(2024, 1, 1, tzinfo=UTC),
            modified_time=datetime(2024, 1, 2, tzinfo=UTC),
        ),
        FileEntry(
            name="deleted.txt",
            path="/Temp/deleted.txt",
            size=10,
            inode=99,
            file_type="deleted",
            is_deleted=True,
            is_allocated=False,
        ),
    ]


def test_parse_returns_filesystem_artefacts(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify FileSystemParser maps FileEntry rows to FILESYSTEM_METADATA."""
    # Arrange
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = _entries()
    parser = FileSystemParser(accessor, mock_audit_logger)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 2
    assert ArtefactCategory.FILESYSTEM_METADATA in result.categories_present
    first = result.artefacts[0]
    assert first.category is ArtefactCategory.FILESYSTEM_METADATA
    assert first.raw_data["filename"] == "hosts"
    assert first.raw_data["inode"] == 42
    assert first.raw_data["is_deleted"] is False
    assert first.metadata["parser"] == "FileSystemParser"
    accessor.close.assert_called_once()
    mock_audit_logger.log_action.assert_called()


def test_parse_enforces_artefact_limit(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify max_artefacts stops the filesystem walk early."""
    # Arrange
    many = [
        FileEntry(name=f"f{i}", path=f"/f{i}", size=1, inode=i, file_type="file")
        for i in range(10)
    ]
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = many
    parser = FileSystemParser(accessor, mock_audit_logger, max_artefacts=3)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 3


def test_parse_wraps_unexpected_errors(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify unexpected accessor failures become DiskParsingError."""
    # Arrange
    accessor = MagicMock()
    accessor.open_image.side_effect = RuntimeError("disk boom")
    parser = FileSystemParser(accessor, mock_audit_logger)

    # Act / Assert
    with pytest.raises(DiskParsingError, match="FileSystemParser failed"):
        parser.parse(sample_evidence_image)
    assert any(
        call.kwargs.get("action") == "PARSE_ERROR"
        for call in mock_audit_logger.log_action.call_args_list
    )


def test_supported_types_and_categories(mock_audit_logger: MagicMock) -> None:
    """Verify parser metadata declarations."""
    # Arrange
    parser = FileSystemParser(MagicMock(), mock_audit_logger)

    # Act / Assert
    assert parser.parser_name == "FileSystemParser"
    assert parser.supported_evidence_types() == [EvidenceType.DISK_IMAGE]
    assert parser.supported_categories() == [ArtefactCategory.FILESYSTEM_METADATA]


def test_iso_or_none_handles_missing_timestamps(mock_audit_logger: MagicMock) -> None:
    """Verify timestamp serialisation helper."""
    # Arrange / Act / Assert
    assert FileSystemParser._iso_or_none(None) is None
    stamp = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    assert FileSystemParser._iso_or_none(stamp) == stamp.isoformat()
