"""Extended CaseService lifecycle and assignment tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.case_management.enums import CaseStatus
from dfat.case_management.exceptions import (
    InvalidCaseTransitionError,
    InvestigatorAlreadyAssignedError,
)
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evidence import CaseMetadata
from dfat.services.case_service import CaseService


def _case(status: CaseStatus, *, investigators=None) -> Case:
    investigators = investigators or []
    return Case(
        metadata=CaseMetadata(case_id="c1", case_name="Case", investigator="Alice"),
        status=status,
        investigators=investigators,
        lead_investigator_id=investigators[0].user_id if investigators else "u1",
    )


def _service(case_repo: AsyncMock | None = None, user_repo: AsyncMock | None = None):
    users = user_repo or AsyncMock()
    users.get = AsyncMock(
        side_effect=lambda user_id: MagicMock(
            id=user_id, username=user_id, full_name=f"User {user_id}"
        )
    )
    return CaseService(
        case_repo=case_repo or AsyncMock(),
        evidence_repo=AsyncMock(),
        user_repo=users,
        audit_service=AsyncMock(),
        custody_service=AsyncMock(),
    )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (CaseStatus.CREATED, CaseStatus.OPEN),
        (CaseStatus.OPEN, CaseStatus.ACTIVE),
        (CaseStatus.ACTIVE, CaseStatus.UNDER_REVIEW),
        (CaseStatus.UNDER_REVIEW, CaseStatus.ACTIVE),
        (CaseStatus.ACTIVE, CaseStatus.CLOSED),
        (CaseStatus.CLOSED, CaseStatus.ARCHIVED),
    ],
)
def test_every_requested_transition_path_is_valid(
    current: CaseStatus, target: CaseStatus
) -> None:
    # Arrange
    service = _service()

    # Act / Assert
    service._validate_transition(current, target)


@pytest.mark.parametrize(
    ("current", "attempted"),
    [
        (CaseStatus.CREATED, CaseStatus.ACTIVE),
        (CaseStatus.OPEN, CaseStatus.ARCHIVED),
        (CaseStatus.ARCHIVED, CaseStatus.OPEN),
    ],
)
def test_invalid_transition_reports_current_and_attempted(
    current: CaseStatus, attempted: CaseStatus
) -> None:
    # Arrange
    service = _service()

    # Act / Assert
    with pytest.raises(InvalidCaseTransitionError) as exc:
        service._validate_transition(current, attempted)
    assert exc.value.current_status == current.value
    assert exc.value.attempted_status == attempted.value


@pytest.mark.asyncio
async def test_assign_two_investigators_then_duplicate_raises() -> None:
    # Arrange
    repo = AsyncMock()
    assignments: list[CaseInvestigator] = []
    current = _case(CaseStatus.OPEN)

    async def add_investigator(_case_id, investigator):
        if any(item.user_id == investigator.user_id for item in assignments):
            raise InvestigatorAlreadyAssignedError(
                "duplicate", context={"case_id": "c1", "user_id": investigator.user_id}
            )
        assignments.append(investigator)

    async def get_case(_case_id):
        current.investigators = list(assignments)
        return current

    repo.get = AsyncMock(side_effect=get_case)
    repo.add_investigator = AsyncMock(side_effect=add_investigator)
    service = _service(repo)

    # Act
    await service.assign_investigator("c1", "u2", "member", "u1")
    result = await service.assign_investigator("c1", "u3", "member", "u1")

    # Assert
    assert {item.user_id for item in result.investigators} == {"u2", "u3"}
    with pytest.raises(InvestigatorAlreadyAssignedError):
        await service.assign_investigator("c1", "u2", "member", "u1")


@pytest.mark.asyncio
async def test_close_case_with_zero_evidence_succeeds() -> None:
    # Arrange
    repo = AsyncMock()
    active = _case(CaseStatus.ACTIVE)
    closed = _case(CaseStatus.CLOSED)
    closed.closure_reason = "done"
    repo.get = AsyncMock(side_effect=[active, closed])
    repo.update_status = AsyncMock(return_value=closed)
    repo.save = AsyncMock(return_value="c1")
    service = _service(repo)

    # Act
    result = await service.close_case("c1", "u1", "done")

    # Assert
    assert result.status is CaseStatus.CLOSED
    assert result.closure_reason == "done"
    service._custody_service.record_seal.assert_not_awaited()


@pytest.mark.asyncio
async def test_reopen_records_reason_and_returns_active_case() -> None:
    # Arrange
    repo = AsyncMock()
    review = _case(CaseStatus.UNDER_REVIEW)
    active = _case(CaseStatus.ACTIVE)
    repo.get = AsyncMock(side_effect=[review, review, review])
    repo.save = AsyncMock(return_value="c1")
    repo.update_status = AsyncMock(return_value=active)
    service = _service(repo)

    # Act
    result = await service.reopen_case("c1", "u1", "new lead")

    # Assert
    assert result.status is CaseStatus.ACTIVE
    saved = repo.save.await_args.args[0]
    assert "Reopened: new lead" in saved.notes
