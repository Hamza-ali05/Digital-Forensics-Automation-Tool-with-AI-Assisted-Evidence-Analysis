"""Unit tests for insert-only CustodyRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dfat.case_management.enums import CustodyAction
from dfat.database.engine import DatabaseEngine
from dfat.database.repositories.custody_repo import CustodyRepository
from dfat.evidence_management.models import ChainOfCustodyRecord


def _record(
    evidence_id: str,
    action: CustodyAction,
    *,
    reason: str = "test",
) -> ChainOfCustodyRecord:
    return ChainOfCustodyRecord(
        evidence_id=evidence_id,
        action=action,
        performed_by_user_id="u1",
        performed_by_name="Alice",
        timestamp=datetime(2024, 1, 15, tzinfo=UTC),
        reason=reason,
        hash_at_action="a" * 64,
    )


@pytest.mark.asyncio
async def test_add_and_get_chain(db_engine: DatabaseEngine) -> None:
    """Adding records returns an ordered custody chain."""
    # Arrange
    repo = CustodyRepository(db_engine.session_factory)

    # Act
    await repo.add_record(_record("ev-c1", CustodyAction.ACQUIRED))
    await repo.add_record(_record("ev-c1", CustodyAction.ACCESSED, reason="read"))
    chain = await repo.get_chain("ev-c1")

    # Assert
    assert len(chain) == 2
    assert chain[0].action is CustodyAction.ACQUIRED
    assert chain[1].action is CustodyAction.ACCESSED


@pytest.mark.asyncio
async def test_sequential_entry_numbers(db_engine: DatabaseEngine) -> None:
    """Entry numbers increment sequentially per evidence ID."""
    # Arrange
    repo = CustodyRepository(db_engine.session_factory)

    # Act
    await repo.add_record(_record("ev-seq", CustodyAction.ACQUIRED))
    await repo.add_record(_record("ev-seq", CustodyAction.ACCESSED))
    await repo.add_record(_record("ev-seq", CustodyAction.ANALYSED))
    chain = await repo.get_chain("ev-seq")

    # Assert
    assert [r.entry_number for r in chain] == [1, 2, 3]


@pytest.mark.asyncio
async def test_no_update_api(db_engine: DatabaseEngine) -> None:
    """CustodyRepository exposes no update/delete methods."""
    # Arrange
    repo = CustodyRepository(db_engine.session_factory)

    # Act / Assert
    assert not hasattr(repo, "update")
    assert not hasattr(repo, "delete")
    assert hasattr(repo, "add_record")
    assert hasattr(repo, "get_chain")


@pytest.mark.asyncio
async def test_count_by_evidence(db_engine: DatabaseEngine) -> None:
    """count_by_evidence returns the number of custody rows."""
    # Arrange
    repo = CustodyRepository(db_engine.session_factory)
    await repo.add_record(_record("ev-cnt", CustodyAction.ACQUIRED))
    await repo.add_record(_record("ev-cnt", CustodyAction.ACCESSED))

    # Act
    count = await repo.count_by_evidence("ev-cnt")

    # Assert
    assert count == 2
    assert await repo.count_by_evidence("missing") == 0
