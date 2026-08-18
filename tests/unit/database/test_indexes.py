"""Tests that catalogued compound indexes exist on created schemas."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from dfat.database.engine import DatabaseEngine
from dfat.database.indexes import COMPOUND_INDEXES, NEW_COMPOUND_INDEXES, apply_indexes


@pytest.mark.asyncio
async def test_create_tables_includes_compound_indexes(
    db_engine: DatabaseEngine,
) -> None:
    """ORM ``create_all`` materialises every documented compound index."""
    async with db_engine.engine.connect() as connection:
        result = await connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        )
        names = {row[0] for row in result.fetchall()}

    for index in COMPOUND_INDEXES:
        assert index.name in names, f"missing index {index.name}"


@pytest.mark.asyncio
async def test_apply_indexes_is_idempotent(db_engine: DatabaseEngine) -> None:
    """``CREATE INDEX IF NOT EXISTS`` can be re-run safely."""
    applied = await apply_indexes(db_engine.engine, indexes=NEW_COMPOUND_INDEXES)
    again = await apply_indexes(db_engine.engine, indexes=NEW_COMPOUND_INDEXES)
    assert applied == again
    assert len(applied) == len(NEW_COMPOUND_INDEXES)
