"""Unit tests for MultiHashService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dfat.core.exceptions import IntegrityVerificationError
from dfat.evidence_management.hash_service import MultiHashService
from dfat.evidence_management.models import HashSet
from dfat.shared.hashing import compute_file_hash
from dfat.core.enums import HashAlgorithm


@pytest.fixture
def hash_service() -> MultiHashService:
    """Return MultiHashService with a mock audit logger."""
    return MultiHashService(MagicMock())


def test_hash_correctness(hash_service: MultiHashService, temp_evidence_file: Path) -> None:
    """Computed digests match independent hashlib/shared.hashing values."""
    # Arrange / Act
    result = hash_service.compute_hash_set(temp_evidence_file, "ev-1")
    expected_sha256 = compute_file_hash(temp_evidence_file, HashAlgorithm.SHA256)

    # Assert
    assert result.sha256 == expected_sha256
    assert len(result.md5) == 32
    assert len(result.sha1) == 40
    assert result.file_size_bytes == 1024


def test_single_pass_reads_file_once(
    hash_service: MultiHashService,
    temp_evidence_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hash set computation opens the evidence file a single time."""
    # Arrange
    opens: list[Path] = []
    real_open = Path.open

    def tracking_open(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == temp_evidence_file:
            opens.append(self)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    # Act
    hash_service.compute_hash_set(temp_evidence_file, "ev-1")

    # Assert
    assert len(opens) == 1


def test_verify_success(hash_service: MultiHashService, temp_evidence_file: Path) -> None:
    """verify_hash_set returns True when digests match."""
    # Arrange
    expected = hash_service.compute_hash_set(temp_evidence_file, "ev-1")

    # Act
    ok = hash_service.verify_hash_set(temp_evidence_file, expected, "ev-1")

    # Assert
    assert ok is True


def test_verify_failure(hash_service: MultiHashService, temp_evidence_file: Path) -> None:
    """verify_hash_set raises IntegrityVerificationError on mismatch."""
    # Arrange
    expected = HashSet(
        md5="0" * 32,
        sha1="1" * 40,
        sha256="f" * 64,
        file_size_bytes=1024,
    )

    # Act / Assert
    with pytest.raises(IntegrityVerificationError):
        hash_service.verify_hash_set(temp_evidence_file, expected, "ev-1")


def test_progress_callback(hash_service: MultiHashService, temp_evidence_file: Path) -> None:
    """Progress callback receives bytes_read/total updates."""
    # Arrange
    progress: list[tuple[int, int]] = []

    # Act
    result = hash_service.compute_hash_set_with_progress(
        temp_evidence_file,
        "ev-1",
        progress_callback=lambda read, total: progress.append((read, total)),
    )

    # Assert
    assert result.file_size_bytes == 1024
    assert progress
    assert progress[-1][0] == 1024
    assert progress[-1][1] == 1024
