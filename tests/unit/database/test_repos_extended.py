"""Extended async repository tests using the in-memory database."""

from __future__ import annotations

import asyncio

import pytest

from dfat.case_management.enums import CaseStatus
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evidence import CaseMetadata
from dfat.database.engine import DatabaseEngine
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository


def _case(case_id: str, creator_id: str, name: str) -> Case:
    investigator = CaseInvestigator(
        user_id=creator_id,
        username="investigator",
        full_name="Test Investigator",
        role="lead",
    )
    return Case(
        metadata=CaseMetadata(
            case_id=case_id, case_name=name, investigator="Test Investigator"
        ),
        investigators=[investigator],
        lead_investigator_id=creator_id,
        tags=[],
        notes=[],
    )


@pytest.mark.asyncio
async def test_empty_case_queries_return_empty_lists(
    db_engine: DatabaseEngine,
    seeded_db: dict,
) -> None:
    # Arrange
    repo = SQLAlchemyCaseRepository(db_engine.session_factory)

    # Act / Assert
    assert await repo.list_all() == []
    assert await repo.get_by_status(CaseStatus.OPEN) == []
    assert await repo.get_by_investigator("missing") == []


@pytest.mark.asyncio
async def test_save_then_get_case_round_trip(
    db_engine: DatabaseEngine,
    seeded_db: dict,
) -> None:
    # Arrange
    repo = SQLAlchemyCaseRepository(db_engine.session_factory)
    user_id = seeded_db["user_ids"]["investigator"]
    case = _case("case-round-trip", user_id, "Round Trip")

    # Act
    saved_id = await repo.save(case, created_by_user_id=user_id)
    restored = await repo.get(saved_id)

    # Assert
    assert restored is not None
    assert restored.case_id == case.case_id
    assert restored.case_name == case.case_name
    assert restored.lead_investigator_id == user_id
    assert len(restored.investigators) == 1


@pytest.mark.asyncio
async def test_concurrent_saves_persist_two_cases(
    db_engine: DatabaseEngine,
    seeded_db: dict,
) -> None:
    # Arrange
    repo = SQLAlchemyCaseRepository(db_engine.session_factory)
    user_id = seeded_db["user_ids"]["investigator"]
    cases = [
        _case("case-concurrent-1", user_id, "First"),
        _case("case-concurrent-2", user_id, "Second"),
    ]

    # Act
    ids = await asyncio.gather(
        *(repo.save(case, created_by_user_id=user_id) for case in cases)
    )
    restored = await repo.list_all()

    # Assert
    assert set(ids) == {"case-concurrent-1", "case-concurrent-2"}
    assert {case.case_id for case in restored} == set(ids)
