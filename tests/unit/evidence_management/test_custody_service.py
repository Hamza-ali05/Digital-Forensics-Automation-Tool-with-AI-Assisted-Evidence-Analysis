"""Unit tests for ChainOfCustodyService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.case_management.enums import CustodyAction
from dfat.core.exceptions import IntegrityVerificationError
from dfat.database.repositories.custody_repo import CustodyRepository
from dfat.evidence_management.custody_service import ChainOfCustodyService
from dfat.evidence_management.hash_service import MultiHashService
from dfat.evidence_management.models import ChainOfCustodyRecord
from dfat.services.audit_service import AuditService


def _service(
    *,
    custody_repo: AsyncMock | None = None,
    evidence_repo: AsyncMock | None = None,
) -> tuple[ChainOfCustodyService, AsyncMock, MultiHashService]:
    hash_svc = MultiHashService(MagicMock())
    repo = custody_repo or AsyncMock()
    audit = AsyncMock(spec=AuditService)
    service = ChainOfCustodyService(
        custody_repo=repo,
        hash_service=hash_svc,
        audit_service=audit,
        evidence_repo=evidence_repo or AsyncMock(),
    )
    return service, repo, hash_svc


@pytest.mark.asyncio
async def test_acquisition_is_first_entry(temp_evidence_file: Path) -> None:
    """record_acquisition creates ACQUIRED entry_number=1."""
    # Arrange
    service, repo, _hash = _service()
    repo.count_by_evidence = AsyncMock(return_value=0)
    repo.add_record = AsyncMock(return_value="r1")
    acquired = ChainOfCustodyRecord(
        evidence_id="ev-1",
        action=CustodyAction.ACQUIRED,
        performed_by_user_id="u1",
        performed_by_name="Alice",
        reason="acq",
        hash_at_action="x",
        entry_number=1,
    )
    repo.get_latest = AsyncMock(return_value=acquired)

    # Act
    result = await service.record_acquisition(
        "ev-1",
        temp_evidence_file,
        "u1",
        "Alice",
        "acq",
    )

    # Assert
    assert result.action is CustodyAction.ACQUIRED
    assert result.entry_number == 1
    repo.add_record.assert_awaited()


@pytest.mark.asyncio
async def test_access_verifies_integrity(temp_evidence_file: Path) -> None:
    """record_access verifies against acquisition baseline before writing."""
    # Arrange
    service, repo, hash_svc = _service()
    digest = hash_svc.compute_hash_set(temp_evidence_file, "ev-1").sha256
    baseline = ChainOfCustodyRecord(
        evidence_id="ev-1",
        action=CustodyAction.ACQUIRED,
        performed_by_user_id="u1",
        performed_by_name="Alice",
        reason="acq",
        hash_at_action=digest,
        entry_number=1,
    )
    accessed = ChainOfCustodyRecord(
        evidence_id="ev-1",
        action=CustodyAction.ACCESSED,
        performed_by_user_id="u2",
        performed_by_name="Bob",
        reason="review",
        hash_at_action=digest,
        entry_number=2,
    )
    repo.get_chain = AsyncMock(return_value=[baseline])
    repo.add_record = AsyncMock(return_value="r2")
    repo.get_latest = AsyncMock(return_value=accessed)

    # Act
    result = await service.record_access(
        "ev-1",
        temp_evidence_file,
        "u2",
        "Bob",
        "review",
    )

    # Assert
    assert result.action is CustodyAction.ACCESSED
    assert result.entry_number == 2


@pytest.mark.asyncio
async def test_valid_chain_verification(temp_evidence_file: Path) -> None:
    """verify_custody_chain accepts sequential matching hashes."""
    # Arrange
    service, repo, hash_svc = _service()
    digest = hash_svc.compute_hash_set(temp_evidence_file, "ev-1").sha256
    chain = [
        ChainOfCustodyRecord(
            evidence_id="ev-1",
            action=CustodyAction.ACQUIRED,
            performed_by_user_id="u1",
            performed_by_name="Alice",
            reason="acq",
            hash_at_action=digest,
            entry_number=1,
        ),
        ChainOfCustodyRecord(
            evidence_id="ev-1",
            action=CustodyAction.ACCESSED,
            performed_by_user_id="u2",
            performed_by_name="Bob",
            reason="review",
            hash_at_action=digest,
            entry_number=2,
        ),
    ]
    repo.get_chain = AsyncMock(return_value=chain)

    # Act
    result = await service.verify_custody_chain("ev-1", temp_evidence_file)

    # Assert
    assert result["is_valid"] is True
    assert result["integrity_verified"] is True
    assert result["total_entries"] == 2
    assert result["issues"] == []


@pytest.mark.asyncio
async def test_integrity_mismatch(temp_evidence_file: Path) -> None:
    """Tampered file yields integrity_verified=False."""
    # Arrange
    service, repo, _hash = _service()
    chain = [
        ChainOfCustodyRecord(
            evidence_id="ev-1",
            action=CustodyAction.ACQUIRED,
            performed_by_user_id="u1",
            performed_by_name="Alice",
            reason="acq",
            hash_at_action="f" * 64,
            entry_number=1,
        )
    ]
    repo.get_chain = AsyncMock(return_value=chain)

    # Act
    result = await service.verify_custody_chain("ev-1", temp_evidence_file)

    # Assert
    assert result["integrity_verified"] is False
    assert result["is_valid"] is False
    assert result["issues"]


@pytest.mark.asyncio
async def test_access_blocked_on_mismatch(temp_evidence_file: Path) -> None:
    """record_access raises when baseline hash no longer matches."""
    # Arrange
    service, repo, _hash = _service()
    repo.get_chain = AsyncMock(
        return_value=[
            ChainOfCustodyRecord(
                evidence_id="ev-1",
                action=CustodyAction.ACQUIRED,
                performed_by_user_id="u1",
                performed_by_name="Alice",
                reason="acq",
                hash_at_action="f" * 64,
                entry_number=1,
            )
        ]
    )

    # Act / Assert
    with pytest.raises(IntegrityVerificationError):
        await service.record_access("ev-1", temp_evidence_file, "u2", "Bob", "bad")


def test_custody_repository_has_no_update_or_delete() -> None:
    """CustodyRepository is insert-only (no update/delete API)."""
    # Arrange / Act / Assert
    assert not hasattr(CustodyRepository, "update")
    assert not hasattr(CustodyRepository, "delete")
    assert not hasattr(CustodyRepository, "remove")
