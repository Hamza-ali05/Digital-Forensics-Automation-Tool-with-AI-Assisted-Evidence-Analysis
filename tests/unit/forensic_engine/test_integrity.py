"""Unit tests for integrity checking."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dfat.core.enums import HashAlgorithm
from dfat.core.exceptions import IntegrityVerificationError
from dfat.forensic_engine.acquisition.integrity import IntegrityChecker
from dfat.shared.hashing import compute_file_hash


def test_compute_initial_hash_returns_sha256_digest(
    tmp_path: Path,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify compute_initial_hash returns a SHA-256 hex digest."""
    # Arrange
    evidence = tmp_path / "sample.dd"
    evidence.write_bytes(b"integrity-test-bytes")
    checker = IntegrityChecker(mock_audit_logger, HashAlgorithm.SHA256)

    # Act
    digest = checker.compute_initial_hash(evidence, "ev-1")

    # Assert
    assert len(digest) == 64
    assert digest == compute_file_hash(evidence, HashAlgorithm.SHA256)
    mock_audit_logger.log_action.assert_called()


def test_verify_integrity_succeeds_when_hash_matches(
    tmp_path: Path,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify integrity verification succeeds for an unmodified file."""
    # Arrange
    evidence = tmp_path / "sample.dd"
    evidence.write_bytes(b"unchanged")
    checker = IntegrityChecker(mock_audit_logger, HashAlgorithm.SHA256)
    expected = checker.compute_initial_hash(evidence, "ev-1")

    # Act
    result = checker.verify_integrity(evidence, expected, "ev-1")

    # Assert
    assert result is True


def test_verify_integrity_raises_when_hash_mismatches(
    tmp_path: Path,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify integrity verification raises on hash mismatch."""
    # Arrange
    evidence = tmp_path / "sample.dd"
    evidence.write_bytes(b"original")
    checker = IntegrityChecker(mock_audit_logger, HashAlgorithm.SHA256)

    # Act / Assert
    with pytest.raises(IntegrityVerificationError):
        checker.verify_integrity(evidence, "b" * 64, "ev-1")
