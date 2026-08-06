"""Unit tests for DatabaseEngine lifecycle helpers."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from dfat.database.engine import DatabaseEngine


@pytest.mark.asyncio
async def test_engine_creation_sqlite(tmp_path) -> None:
    """Verify DatabaseEngine creates successfully with a SQLite URL."""
    # Arrange
    db_path = tmp_path / "engine.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    # Act
    engine = DatabaseEngine(database_url=url, echo=False)

    # Assert
    assert engine.engine is not None
    assert engine.session_factory is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_engine_check_connection(db_engine: DatabaseEngine) -> None:
    """Verify check_connection returns True for a live engine."""
    # Arrange / Act
    ok = await db_engine.check_connection()

    # Assert
    assert ok is True


@pytest.mark.asyncio
async def test_engine_create_tables(db_engine: DatabaseEngine) -> None:
    """Verify create_tables registers expected core tables."""
    # Arrange / Act
    async with db_engine.engine.connect() as connection:
        result = await connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tables = {row[0] for row in result.fetchall()}

    # Assert
    assert "users" in tables
    assert "roles" in tables
    assert "evidence_records" in tables
    assert "audit_log" in tables


@pytest.mark.asyncio
async def test_engine_session_context(db_engine: DatabaseEngine) -> None:
    """Verify get_session yields a usable session and closes cleanly."""
    # Arrange / Act
    agen = db_engine.get_session()
    session = await agen.__anext__()
    result = await session.execute(text("SELECT 1"))
    value = result.scalar_one()
    try:
        await agen.__anext__()
    except StopAsyncIteration:
        pass

    # Assert
    assert value == 1
