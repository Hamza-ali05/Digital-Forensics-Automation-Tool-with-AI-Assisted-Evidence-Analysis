"""Unit tests for BrowserHistoryParser with mocked disk access and SQLite DBs."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.browser import BrowserHistoryParser
from dfat.forensic_engine.parsers.disk_access import FileEntry


def _chrome_history_db(path: Path, rows: int = 3) -> Path:
    """Create a tiny Chrome-style History SQLite database."""
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE urls ("
            "url TEXT, title TEXT, visit_count INTEGER, last_visit_time INTEGER)"
        )
        for index in range(rows):
            conn.execute(
                "INSERT INTO urls VALUES (?, ?, ?, ?)",
                (
                    f"https://example.com/{index}",
                    f"Page {index}",
                    index + 1,
                    13300000000000000 + index,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return path


def test_parse_returns_browser_history_artefacts(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify Chrome History rows become BROWSER_HISTORY artefacts."""
    # Arrange
    db_path = _chrome_history_db(tmp_path / "History", rows=2)
    entry = FileEntry(
        name="History",
        path="/Users/alice/AppData/Local/Google/Chrome/User Data/Default/History",
        size=db_path.stat().st_size,
        inode=11,
        file_type="file",
    )
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = [entry]
    accessor.extract_file_to_temp.return_value = db_path
    parser = BrowserHistoryParser(accessor, mock_audit_logger)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 2
    art = result.artefacts[0]
    assert art.category is ArtefactCategory.BROWSER_HISTORY
    assert art.raw_data["browser_type"] == "chrome"
    assert art.raw_data["url"].startswith("https://example.com/")
    assert art.raw_data["profile"] == "Default"


def test_parse_skips_corrupt_database(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify corrupt SQLite databases are skipped gracefully."""
    # Arrange
    bad = tmp_path / "History"
    bad.write_bytes(b"not-a-sqlite-db")
    entry = FileEntry(
        name="History",
        path="/Users/bob/AppData/Local/Google/Chrome/User Data/Default/History",
        size=10,
        inode=12,
        file_type="file",
    )
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = [entry]
    accessor.extract_file_to_temp.return_value = bad
    parser = BrowserHistoryParser(accessor, mock_audit_logger)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 0


def test_parse_enforces_artefact_limit(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify browser query respects max_artefacts."""
    # Arrange
    db_path = _chrome_history_db(tmp_path / "History", rows=5)
    entry = FileEntry(
        name="History",
        path="/Users/alice/AppData/Local/Microsoft/Edge/User Data/Default/History",
        size=db_path.stat().st_size,
        inode=13,
        file_type="file",
    )
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = [entry]
    accessor.extract_file_to_temp.return_value = db_path
    parser = BrowserHistoryParser(accessor, mock_audit_logger, max_artefacts=2)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 2
    assert all(a.raw_data["browser_type"] == "edge" for a in result.artefacts)


def test_open_image_failure_raises_disk_parsing_error(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify unexpected accessor errors become DiskParsingError."""
    # Arrange
    accessor = MagicMock()
    accessor.open_image.side_effect = RuntimeError("cannot open")
    parser = BrowserHistoryParser(accessor, mock_audit_logger)

    # Act / Assert
    with pytest.raises(DiskParsingError):
        parser.parse(sample_evidence_image)
    assert parser.parser_name == "BrowserHistoryParser"
    assert parser.supported_evidence_types() == [EvidenceType.DISK_IMAGE]
    assert parser.supported_categories() == [ArtefactCategory.BROWSER_HISTORY]
