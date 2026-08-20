"""Unit tests for DatabaseInitializer."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from dfat.bootstrap.database_initializer import DatabaseInitializer
from dfat.bootstrap.models import InitPhase, InitStatus
from dfat.database.engine import DatabaseEngine
from dfat.database.models.user import RoleORM
from dfat.settings import DatabaseSettings


@pytest.mark.asyncio
async def test_initialize_applies_schema_and_seeds(tmp_path: Path) -> None:
    db_path = tmp_path / "dfat.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    settings = DatabaseSettings(url=url, create_tables_on_startup=True, echo=False)
    engine = DatabaseEngine(database_url=url, echo=False)
    try:
        result = await DatabaseInitializer(engine, settings).initialize()
        assert result.phase == InitPhase.DATABASE
        assert result.status == InitStatus.COMPLETED
        assert result.details.get("connectivity") is True
        assert result.details.get("seed_roles_ok") is True
        assert result.details.get("migration_revision") is not None
        assert result.details.get("missing_tables") == []

        async with engine.session_factory() as session:
            names = set((await session.execute(select(RoleORM.name))).scalars().all())
        assert names >= {"admin", "investigator", "analyst", "viewer"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_connection_failure_returns_clear_error() -> None:
    url = "sqlite+aiosqlite:////nonexistent_drive_path_dfat_xyz/nope.db"
    # Use an invalid postgres host instead for a reliable connection failure.
    url = "postgresql+asyncpg://invalid:invalid@127.0.0.1:1/dfat_missing"
    settings = DatabaseSettings(url=url, create_tables_on_startup=False, echo=False)
    engine = DatabaseEngine(database_url=url, echo=False, pool_size=1, max_overflow=0)
    try:
        result = await DatabaseInitializer(engine, settings).initialize()
        assert result.status == InitStatus.FAILED
        assert result.error is not None
        assert "connection" in result.error.lower() or "Database" in result.error
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_seed_verification_inserts_missing_roles(tmp_path: Path) -> None:
    db_path = tmp_path / "seed.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    settings = DatabaseSettings(url=url, create_tables_on_startup=True, echo=False)
    engine = DatabaseEngine(database_url=url, echo=False)
    try:
        await engine.create_tables()
        # Only one role present — initializer should add the rest.
        async with engine.session_factory() as session:
            session.add(
                RoleORM(
                    id="role-admin",
                    name="admin",
                    description="Full system administrator",
                    permissions='{"all": true}',
                    is_active=True,
                )
            )
            await session.commit()

        result = await DatabaseInitializer(engine, settings).initialize()
        assert result.status == InitStatus.COMPLETED
        async with engine.session_factory() as session:
            names = set((await session.execute(select(RoleORM.name))).scalars().all())
        assert names == {"admin", "investigator", "analyst", "viewer"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_initialize_is_idempotent(tmp_path: Path) -> None:
    """Running database initialization twice leaves the schema and roles intact."""
    db_path = tmp_path / "idempotent.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    settings = DatabaseSettings(url=url, create_tables_on_startup=True, echo=False)
    engine = DatabaseEngine(database_url=url, echo=False)
    try:
        first = await DatabaseInitializer(engine, settings).initialize()
        second = await DatabaseInitializer(engine, settings).initialize()

        assert first.status == InitStatus.COMPLETED
        assert second.status == InitStatus.COMPLETED
        assert second.details.get("connectivity") is True
        assert second.details.get("seed_roles_ok") is True
        assert second.details.get("missing_tables") == []

        async with engine.session_factory() as session:
            names = set((await session.execute(select(RoleORM.name))).scalars().all())
        assert names == {"admin", "investigator", "analyst", "viewer"}
    finally:
        await engine.dispose()
