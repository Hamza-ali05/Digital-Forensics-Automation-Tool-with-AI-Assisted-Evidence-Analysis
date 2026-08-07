"""Unit tests for SQLAlchemyCaseRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from dfat.case_management.enums import CaseStatus
from dfat.case_management.exceptions import InvestigatorAlreadyAssignedError
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evidence import CaseMetadata
from dfat.database.engine import DatabaseEngine
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository


def _case(
    case_id: str,
    *,
    status: CaseStatus = CaseStatus.CREATED,
    lead: str | None = None,
) -> Case:
    return Case(
        metadata=CaseMetadata(
            case_id=case_id,
            case_name=f"Case {case_id}",
            investigator="Tester",
            description="repo test",
            created_at=datetime(2024, 1, 15, tzinfo=UTC),
        ),
        status=status,
        lead_investigator_id=lead,
    )


@pytest.mark.asyncio
async def test_save_and_get(db_engine: DatabaseEngine, seeded_db: dict[str, Any]) -> None:
    """Saving a case allows loading it by ID."""
    # Arrange
    repo = SQLAlchemyCaseRepository(db_engine.session_factory)
    user_id = seeded_db["user_ids"]["investigator"]
    case = _case("case-repo-1", lead=user_id)

    # Act
    await repo.save(case, created_by_user_id=user_id)
    loaded = await repo.get("case-repo-1")

    # Assert
    assert loaded is not None
    assert loaded.case_id == "case-repo-1"
    assert loaded.case_name == "Case case-repo-1"


@pytest.mark.asyncio
async def test_list_by_status(db_engine: DatabaseEngine, seeded_db: dict[str, Any]) -> None:
    """get_by_status filters cases by lifecycle status."""
    # Arrange
    repo = SQLAlchemyCaseRepository(db_engine.session_factory)
    user_id = seeded_db["user_ids"]["investigator"]
    await repo.save(_case("case-open-1"), created_by_user_id=user_id)
    await repo.update_status("case-open-1", CaseStatus.OPEN)

    # Act
    opened = await repo.get_by_status(CaseStatus.OPEN)
    created = await repo.get_by_status(CaseStatus.CREATED)

    # Assert
    assert any(c.case_id == "case-open-1" for c in opened)
    assert all(c.status is CaseStatus.OPEN for c in opened)


@pytest.mark.asyncio
async def test_get_by_investigator(
    db_engine: DatabaseEngine,
    seeded_db: dict[str, Any],
) -> None:
    """get_by_investigator returns cases for an active assignment."""
    # Arrange
    repo = SQLAlchemyCaseRepository(db_engine.session_factory)
    user_id = seeded_db["user_ids"]["investigator"]
    await repo.save(_case("case-inv-1"), created_by_user_id=user_id)
    await repo.add_investigator(
        "case-inv-1",
        CaseInvestigator(
            user_id=user_id,
            username="investigator",
            full_name="Test Investigator",
            role="lead",
        ),
    )

    # Act
    cases = await repo.get_by_investigator(user_id)

    # Assert
    assert any(c.case_id == "case-inv-1" for c in cases)


@pytest.mark.asyncio
async def test_add_investigator(
    db_engine: DatabaseEngine,
    seeded_db: dict[str, Any],
) -> None:
    """add_investigator assigns a lead and rejects duplicates."""
    # Arrange
    repo = SQLAlchemyCaseRepository(db_engine.session_factory)
    user_id = seeded_db["user_ids"]["investigator"]
    await repo.save(_case("case-add-1"), created_by_user_id=user_id)
    investigator = CaseInvestigator(
        user_id=user_id,
        username="investigator",
        full_name="Test Investigator",
        role="lead",
    )

    # Act
    await repo.add_investigator("case-add-1", investigator)
    loaded = await repo.get("case-add-1")

    # Assert
    assert loaded is not None
    assert loaded.lead_investigator_id == user_id
    with pytest.raises(InvestigatorAlreadyAssignedError):
        await repo.add_investigator("case-add-1", investigator)


@pytest.mark.asyncio
async def test_soft_remove_investigator(
    db_engine: DatabaseEngine,
    seeded_db: dict[str, Any],
) -> None:
    """remove_investigator soft-deletes the assignment."""
    # Arrange
    repo = SQLAlchemyCaseRepository(db_engine.session_factory)
    user_id = seeded_db["user_ids"]["investigator"]
    member_id = seeded_db["user_ids"]["analyst"]
    await repo.save(_case("case-rm-1", lead=user_id), created_by_user_id=user_id)
    await repo.add_investigator(
        "case-rm-1",
        CaseInvestigator(
            user_id=member_id,
            username="analyst",
            full_name="Test Analyst",
            role="member",
        ),
    )

    # Act
    removed = await repo.remove_investigator("case-rm-1", member_id)
    loaded = await repo.get("case-rm-1")

    # Assert
    assert removed is True
    assert loaded is not None
    assert all(inv.user_id != member_id for inv in loaded.investigators)
