"""Unit tests for dual-write AuditService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import PipelineStage
from dfat.core.models.pipeline import AuditEntry
from dfat.services.audit_service import AuditService


@pytest.mark.asyncio
async def test_log_action_writes_to_both() -> None:
    """log_action writes to both the DB repo and file logger."""
    # Arrange
    audit_repo = AsyncMock()
    audit_repo.get_latest_entry_number.return_value = 0
    file_logger = MagicMock()
    service = AuditService(audit_repo, file_logger)

    # Act
    await service.log_action(
        PipelineStage.ACQUISITION,
        "TEST_ACTION",
        evidence_id="ev-1",
        user_id="user-1",
        details={"k": 1},
    )

    # Assert
    audit_repo.log_entry.assert_awaited_once()
    file_logger.log_action.assert_called_once()
    kwargs = file_logger.log_action.call_args.kwargs
    assert kwargs["action"] == "TEST_ACTION"
    assert kwargs["evidence_id"] == "ev-1"


@pytest.mark.asyncio
async def test_get_audit_trail() -> None:
    """get_audit_trail returns repository entries for an evidence ID."""
    # Arrange
    entries = [
        AuditEntry(
            entry_number=1,
            stage=PipelineStage.ACQUISITION,
            action="A",
            evidence_id="ev-1",
        )
    ]
    audit_repo = AsyncMock()
    audit_repo.get_by_evidence.return_value = entries
    service = AuditService(audit_repo, MagicMock())

    # Act
    result = await service.get_audit_trail("ev-1")

    # Assert
    assert result == entries
    audit_repo.get_by_evidence.assert_awaited_once_with("ev-1")


@pytest.mark.asyncio
async def test_verify_trail_integrity() -> None:
    """verify_trail_integrity passes when file and DB trails are consistent."""
    # Arrange
    audit_repo = AsyncMock()
    audit_repo.get_by_evidence.return_value = [
        AuditEntry(
            entry_number=1,
            stage=PipelineStage.ACQUISITION,
            action="A",
            evidence_id="ev-1",
        ),
        AuditEntry(
            entry_number=2,
            stage=PipelineStage.PARSING,
            action="B",
            evidence_id="ev-1",
        ),
    ]
    file_logger = MagicMock()
    file_logger.verify_audit_integrity.return_value = True
    service = AuditService(audit_repo, file_logger)

    # Act
    ok = await service.verify_trail_integrity("ev-1")

    # Assert
    assert ok is True
    file_logger.verify_audit_integrity.assert_called_once()
