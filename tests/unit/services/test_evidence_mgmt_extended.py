"""Extended tests for the composed evidence-management service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.case_management.enums import CaseStatus, EvidenceStatus
from dfat.core.enums import EvidenceType
from dfat.core.models.case import Case
from dfat.core.models.evidence import EvidenceImage
from dfat.evidence_management.exceptions import (
    EvidenceManagementError,
    EvidenceValidationError,
)
from dfat.services.evidence_management_service import EvidenceManagementService


def _service() -> tuple[EvidenceManagementService, dict[str, MagicMock]]:
    deps = {
        name: MagicMock()
        for name in (
            "evidence_service",
            "validation_service",
            "hash_service",
            "custody_service",
            "metadata_repo",
            "status_repo",
            "evidence_repo",
            "case_repo",
            "audit_service",
        )
    }
    for dep in deps.values():
        dep.mock_add_spec([])
    service = EvidenceManagementService(
        evidence_service=deps["evidence_service"],
        validation_service=deps["validation_service"],
        hash_service=deps["hash_service"],
        custody_service=deps["custody_service"],
        metadata_repo=deps["metadata_repo"],
        status_repo=deps["status_repo"],
        evidence_repo=deps["evidence_repo"],
        case_repo=deps["case_repo"],
        audit_service=deps["audit_service"],
    )
    return service, deps


@pytest.mark.asyncio
async def test_register_and_validate_soft_fails_validation(
    sample_case: Case,
    sample_evidence_image: EvidenceImage,
    sample_custody_record,
) -> None:
    # Arrange
    service, deps = _service()
    sample_case.status = CaseStatus.OPEN
    deps["case_repo"].get = AsyncMock(return_value=sample_case)
    deps["evidence_service"].register_evidence = AsyncMock(
        return_value=sample_evidence_image
    )
    deps["status_repo"].add_status_change = AsyncMock()
    deps["custody_service"].record_acquisition = AsyncMock(
        return_value=sample_custody_record
    )
    deps["validation_service"].validate_evidence = AsyncMock(
        side_effect=EvidenceValidationError(
            "invalid", validation_failures=["bad format"]
        )
    )
    deps["metadata_repo"].get_metadata = AsyncMock(return_value=None)
    deps["case_repo"].add_evidence_id = AsyncMock()
    deps["audit_service"].log_action = AsyncMock()

    # Act
    result = await service.register_and_validate(
        sample_evidence_image.file_path,
        sample_case.case_id,
        EvidenceType.DISK_IMAGE,
        None,
        "u1",
        "Alice",
    )

    # Assert
    assert result["validation_passed"] is False
    assert result["validation_failures"] == ["bad format"]
    deps["case_repo"].add_evidence_id.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [CaseStatus.CREATED, CaseStatus.CLOSED, CaseStatus.ARCHIVED])
async def test_register_rejects_ineligible_case_status(
    sample_case: Case, status: CaseStatus
) -> None:
    # Arrange
    service, deps = _service()
    sample_case.status = status
    deps["case_repo"].get = AsyncMock(return_value=sample_case)

    # Act / Assert
    with pytest.raises(EvidenceManagementError):
        await service.register_and_validate(
            "e.dd", sample_case.case_id, EvidenceType.DISK_IMAGE, None, "u1", "Alice"
        )


@pytest.mark.asyncio
async def test_quarantine_is_idempotent_when_already_quarantined(
    sample_evidence_image: EvidenceImage,
) -> None:
    # Arrange
    service, deps = _service()
    deps["evidence_repo"].get = AsyncMock(return_value=sample_evidence_image)
    deps["status_repo"].get_current_status = AsyncMock(
        return_value=EvidenceStatus.QUARANTINED
    )
    deps["status_repo"].add_status_change = AsyncMock()
    deps["audit_service"].log_action = AsyncMock()

    # Act
    result = await service.quarantine_evidence("ev-1", "u1", "still unsafe")

    # Assert
    assert result.previous_status is result.new_status is EvidenceStatus.QUARANTINED
    deps["status_repo"].add_status_change.assert_not_awaited()
    deps["audit_service"].log_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_evidence_success_and_soft_failure(
    sample_evidence_image: EvidenceImage,
) -> None:
    # Arrange
    service, deps = _service()
    metadata = MagicMock()
    deps["evidence_service"].get_evidence = AsyncMock(
        return_value=sample_evidence_image
    )
    deps["validation_service"].revalidate_evidence = AsyncMock(
        side_effect=[
            metadata,
            EvidenceValidationError("bad", validation_failures=["hash mismatch"]),
        ]
    )
    deps["metadata_repo"].save_metadata = AsyncMock()
    deps["metadata_repo"].get_metadata = AsyncMock(return_value=metadata)

    # Act
    passed = await service.validate_evidence(sample_evidence_image.evidence_id, "u1")
    failed = await service.validate_evidence(sample_evidence_image.evidence_id, "u1")

    # Assert
    assert passed["validation_passed"] is True
    assert failed["validation_passed"] is False
    assert failed["validation_failures"] == ["hash mismatch"]
