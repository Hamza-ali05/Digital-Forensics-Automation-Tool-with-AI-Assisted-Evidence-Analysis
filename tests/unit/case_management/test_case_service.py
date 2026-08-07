"""Unit tests for CaseService with mocked repositories."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.case_management.enums import CaseStatus, CustodyAction
from dfat.case_management.exceptions import (
    InvalidCaseTransitionError,
    InvestigatorAlreadyAssignedError,
    NoLeadInvestigatorError,
)
from dfat.core.enums import EvidenceType, HashAlgorithm
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.evidence_management.models import ChainOfCustodyRecord
from dfat.services.case_service import CaseService


def _case(
    *,
    status: CaseStatus = CaseStatus.CREATED,
    lead: str | None = None,
    evidence_ids: list[str] | None = None,
    investigators: list[CaseInvestigator] | None = None,
) -> Case:
    return Case(
        metadata=CaseMetadata(
            case_id="c1",
            case_name="Test",
            investigator="Alice",
            description="d",
        ),
        status=status,
        lead_investigator_id=lead,
        evidence_ids=evidence_ids or [],
        investigators=investigators or [],
    )


def _service(
    *,
    case_repo: AsyncMock | None = None,
    evidence_repo: AsyncMock | None = None,
    user_repo: AsyncMock | None = None,
    audit: AsyncMock | None = None,
    custody: AsyncMock | None = None,
) -> CaseService:
    user = MagicMock(id="u1", username="alice", full_name="Alice")
    urepo = user_repo or AsyncMock()
    urepo.get = AsyncMock(return_value=user)
    return CaseService(
        case_repo=case_repo or AsyncMock(),
        evidence_repo=evidence_repo or AsyncMock(),
        user_repo=urepo,
        audit_service=audit or AsyncMock(),
        custody_service=custody or AsyncMock(),
    )


@pytest.mark.asyncio
async def test_create_case() -> None:
    """create_case persists a CREATED case and audits."""
    # Arrange
    created = _case()
    case_repo = AsyncMock()
    case_repo.save = AsyncMock(return_value="c1")
    case_repo.get = AsyncMock(return_value=created)
    audit = AsyncMock()
    service = _service(case_repo=case_repo, audit=audit)

    # Act
    result = await service.create_case("Test", "d", "u1")

    # Assert
    assert result.status is CaseStatus.CREATED
    case_repo.save.assert_awaited()
    audit.log_action.assert_awaited()


@pytest.mark.asyncio
async def test_open_without_lead_raises() -> None:
    """open_case raises NoLeadInvestigatorError when no lead is set."""
    # Arrange
    case_repo = AsyncMock()
    case_repo.get = AsyncMock(return_value=_case(lead=None))
    service = _service(case_repo=case_repo)

    # Act / Assert
    with pytest.raises(NoLeadInvestigatorError):
        await service.open_case("c1", "u1")


@pytest.mark.asyncio
async def test_open_with_lead() -> None:
    """open_case succeeds when a lead investigator is assigned."""
    # Arrange
    lead = CaseInvestigator(
        user_id="u1",
        username="alice",
        full_name="Alice",
        role="lead",
    )
    case_repo = AsyncMock()
    case_repo.get = AsyncMock(return_value=_case(lead="u1", investigators=[lead]))
    opened = _case(status=CaseStatus.OPEN, lead="u1", investigators=[lead])
    case_repo.update_status = AsyncMock(return_value=opened)
    service = _service(case_repo=case_repo)

    # Act
    result = await service.open_case("c1", "u1")

    # Assert
    assert result.status is CaseStatus.OPEN


@pytest.mark.asyncio
async def test_invalid_transition() -> None:
    """CREATED → ACTIVE is rejected."""
    # Arrange
    service = _service()

    # Act / Assert
    with pytest.raises(InvalidCaseTransitionError) as exc:
        service._validate_transition(CaseStatus.CREATED, CaseStatus.ACTIVE)
    assert exc.value.current_status == "created"
    assert exc.value.attempted_status == "active"


@pytest.mark.asyncio
async def test_close_seals_evidence(tmp_path: Path) -> None:
    """close_case seals custody for linked evidence."""
    # Arrange
    path = tmp_path / "e.dd"
    path.write_bytes(b"data")
    evidence = EvidenceImage(
        evidence_id="e1",
        file_path=path,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="abc",
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=4,
        case=CaseMetadata(case_id="c1", case_name="Test", investigator="Alice"),
    )
    active = _case(status=CaseStatus.ACTIVE, lead="u1", evidence_ids=["e1"])
    closed = _case(status=CaseStatus.CLOSED, lead="u1", evidence_ids=["e1"])
    closed.closure_reason = "done"
    case_repo = AsyncMock()
    case_repo.get = AsyncMock(side_effect=[active, closed, closed])
    case_repo.update_status = AsyncMock(return_value=closed)
    case_repo.save = AsyncMock(return_value="c1")
    evidence_repo = AsyncMock()
    evidence_repo.get = AsyncMock(return_value=evidence)
    custody = AsyncMock()
    custody.get_custody_chain = AsyncMock(
        return_value=[
            ChainOfCustodyRecord(
                evidence_id="e1",
                action=CustodyAction.ACQUIRED,
                performed_by_user_id="u1",
                performed_by_name="Alice",
                reason="acq",
                hash_at_action="abc",
                entry_number=1,
            )
        ]
    )
    custody.record_seal = AsyncMock(
        return_value=ChainOfCustodyRecord(
            evidence_id="e1",
            action=CustodyAction.SEALED,
            performed_by_user_id="u1",
            performed_by_name="Alice",
            reason="done",
            hash_at_action="abc",
            entry_number=2,
        )
    )
    service = _service(
        case_repo=case_repo,
        evidence_repo=evidence_repo,
        custody=custody,
    )

    # Act
    result = await service.close_case("c1", "u1", "done")

    # Assert
    assert result.status is CaseStatus.CLOSED
    custody.record_seal.assert_awaited()


@pytest.mark.asyncio
async def test_full_lifecycle() -> None:
    """Happy-path status transitions through reopen."""
    # Arrange
    lead = CaseInvestigator(
        user_id="u1",
        username="alice",
        full_name="Alice",
        role="lead",
    )
    case_repo = AsyncMock()
    service = _service(case_repo=case_repo)

    created = _case(lead="u1", investigators=[lead])
    opened = _case(status=CaseStatus.OPEN, lead="u1", investigators=[lead])
    active = _case(status=CaseStatus.ACTIVE, lead="u1", investigators=[lead])
    review = _case(status=CaseStatus.UNDER_REVIEW, lead="u1", investigators=[lead])

    # Each public method gets once to validate, then `_transition` gets again.
    case_repo.get = AsyncMock(
        side_effect=[
            created,
            created,  # open_case
            opened,
            opened,  # activate_case
            active,
            active,  # submit_for_review
            review,
            review,  # reopen_case
        ]
    )
    case_repo.update_status = AsyncMock(
        side_effect=[opened, active, review, active]
    )
    case_repo.save = AsyncMock(return_value="c1")

    # Act / Assert
    assert (await service.open_case("c1", "u1")).status is CaseStatus.OPEN
    assert (await service.activate_case("c1", "u1")).status is CaseStatus.ACTIVE
    assert (await service.submit_for_review("c1", "u1")).status is CaseStatus.UNDER_REVIEW
    assert (await service.reopen_case("c1", "u1", "more")).status is CaseStatus.ACTIVE


@pytest.mark.asyncio
async def test_duplicate_investigator_raises() -> None:
    """assign_investigator propagates InvestigatorAlreadyAssignedError."""
    # Arrange
    case_repo = AsyncMock()
    case_repo.get = AsyncMock(return_value=_case(status=CaseStatus.OPEN, lead="u1"))
    case_repo.add_investigator = AsyncMock(
        side_effect=InvestigatorAlreadyAssignedError(
            "Investigator already assigned to case",
            context={"case_id": "c1", "user_id": "u2"},
        )
    )
    service = _service(case_repo=case_repo)

    # Act / Assert
    with pytest.raises(InvestigatorAlreadyAssignedError):
        await service.assign_investigator("c1", "u2", "member", "u1")
