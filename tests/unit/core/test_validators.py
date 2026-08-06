"""Unit tests for core validators."""

from __future__ import annotations

from pathlib import Path

import pytest

from dfat.core.enums import HashAlgorithm
from dfat.core.exceptions import EvidenceNotFoundError
from dfat.core.validators import (
    SUPPORTED_DISK_EXTENSIONS,
    validate_evidence_path,
    validate_file_extension,
    validate_hash_format,
)


def test_validate_hash_format_accepts_valid_sha256() -> None:
    """Verify a 64-character hex string is accepted for SHA-256."""
    # Arrange
    digest = "a" * 64

    # Act
    result = validate_hash_format(digest, HashAlgorithm.SHA256)

    # Assert
    assert result is True


def test_validate_hash_format_rejects_wrong_length() -> None:
    """Verify hash validation fails when digest length is incorrect."""
    # Arrange / Act / Assert
    assert validate_hash_format("abcd", HashAlgorithm.SHA256) is False


def test_validate_evidence_path_raises_when_missing(tmp_path: Path) -> None:
    """Verify missing evidence paths raise EvidenceNotFoundError."""
    # Arrange
    missing = tmp_path / "missing.dd"

    # Act / Assert
    with pytest.raises(EvidenceNotFoundError):
        validate_evidence_path(missing)


def test_validate_file_extension_accepts_dd() -> None:
    """Verify .dd is accepted as a supported disk extension."""
    # Arrange / Act / Assert
    assert validate_file_extension(Path("disk.dd"), SUPPORTED_DISK_EXTENSIONS) is True
