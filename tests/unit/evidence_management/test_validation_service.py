"""Unit tests for EvidenceValidationService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.case_management.enums import EvidenceStatus
from dfat.core.enums import EvidenceType
from dfat.evidence_management.exceptions import EvidenceValidationError
from dfat.evidence_management.hash_service import MultiHashService
from dfat.evidence_management.mime_identifier import MIMEIdentifier
from dfat.evidence_management.validation_service import EvidenceValidationService
from dfat.settings import load_settings


def _service(
    *,
    status_repo: AsyncMock | None = None,
    metadata_repo: AsyncMock | None = None,
) -> tuple[EvidenceValidationService, AsyncMock]:
    status = status_repo or AsyncMock()
    status.get_current_status = AsyncMock(return_value=EvidenceStatus.REGISTERED)
    status.add_status_change = AsyncMock(return_value="chg-1")
    service = EvidenceValidationService(
        mime_identifier=MIMEIdentifier(),
        hash_service=MultiHashService(MagicMock()),
        evidence_status_repo=status,
        audit_logger=MagicMock(),
        settings=load_settings(),
        evidence_metadata_repo=metadata_repo or AsyncMock(),
    )
    return service, status


@pytest.mark.asyncio
async def test_valid_file(temp_evidence_file: Path) -> None:
    """Valid disk image transitions to VALIDATED and returns metadata."""
    # Arrange
    service, status = _service()

    # Act
    metadata = await service.validate_evidence(
        "ev-1",
        temp_evidence_file,
        EvidenceType.DISK_IMAGE,
        "u1",
    )

    # Assert
    assert metadata.is_valid_format is True
    assert metadata.file_size_bytes == 1024
    assert status.add_status_change.await_count >= 2


@pytest.mark.asyncio
async def test_nonexistent_file(tmp_path: Path) -> None:
    """Missing files quarantine and raise EvidenceValidationError."""
    # Arrange
    service, status = _service()
    missing = tmp_path / "missing.dd"

    # Act / Assert
    with pytest.raises(EvidenceValidationError) as exc:
        await service.validate_evidence(
            "ev-1",
            missing,
            EvidenceType.DISK_IMAGE,
            "u1",
        )
    assert any("not found" in msg.lower() for msg in exc.value.validation_failures)
    assert status.add_status_change.await_count >= 2


@pytest.mark.asyncio
async def test_zero_byte_file(tmp_path: Path) -> None:
    """Empty files fail validation and are quarantined."""
    # Arrange
    service, _status = _service()
    empty = tmp_path / "empty.dd"
    empty.write_bytes(b"")

    # Act / Assert
    with pytest.raises(EvidenceValidationError) as exc:
        await service.validate_evidence(
            "ev-1",
            empty,
            EvidenceType.DISK_IMAGE,
            "u1",
        )
    assert any("empty" in msg.lower() for msg in exc.value.validation_failures)


@pytest.mark.asyncio
async def test_mime_notes_on_valid_file(temp_evidence_file: Path) -> None:
    """Successful validation records MIME detection notes."""
    # Arrange
    service, _status = _service()

    # Act
    metadata = await service.validate_evidence(
        "ev-1",
        temp_evidence_file,
        EvidenceType.DISK_IMAGE,
        "u1",
    )

    # Assert
    assert any("MIME" in note for note in metadata.validation_notes)
    assert metadata.mime_type


@pytest.mark.asyncio
async def test_status_transitions_registered_to_validated(
    temp_evidence_file: Path,
) -> None:
    """Validation records REGISTERED→VALIDATING→VALIDATED."""
    # Arrange
    service, status = _service()

    # Act
    await service.validate_evidence(
        "ev-1",
        temp_evidence_file,
        EvidenceType.DISK_IMAGE,
        "u1",
    )

    # Assert
    changes = [call.args[0] for call in status.add_status_change.await_args_list]
    statuses = [(c.previous_status, c.new_status) for c in changes]
    assert (EvidenceStatus.REGISTERED, EvidenceStatus.VALIDATING) in statuses
    assert (EvidenceStatus.VALIDATING, EvidenceStatus.VALIDATED) in statuses
