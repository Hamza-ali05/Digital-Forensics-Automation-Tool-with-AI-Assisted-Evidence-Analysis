"""Alembic environment for DFAT async SQLAlchemy migrations."""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure ``src`` is on sys.path when Alembic is invoked from the project root.
_SRC_ROOT = Path(__file__).resolve().parents[3]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from dfat.database.base import Base  # noqa: E402
from dfat.database.models import (  # noqa: E402, F401 — populate Base.metadata
    AIAnalysisRecordORM,
    ArtefactRecordORM,
    AuditLogRecordORM,
    BenchmarkRecordORM,
    CaseInvestigatorORM,
    CaseORM,
    ChainOfCustodyORM,
    EvidenceMetadataORM,
    EvidenceRecordORM,
    EvidenceStatusHistoryORM,
    PipelineJobORM,
    ReportRecordORM,
    RoleORM,
    SessionORM,
    UsabilityRecordORM,
    UserORM,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Resolve the database URL from DFAT settings, falling back to alembic.ini.

    Returns:
        Async SQLAlchemy database URL.
    """
    try:
        from dfat.settings import load_settings

        return load_settings().database.url
    except Exception:  # noqa: BLE001
        url = config.get_main_option("sqlalchemy.url")
        if not url:
            raise RuntimeError("No database URL configured for Alembic") from None
        return url


def run_migrations_offline() -> None:
    """Run migrations in offline mode (emit SQL without a live connection)."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure Alembic context and run migrations on a sync connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations online using an async SQLAlchemy engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entrypoint for online (connected) migrations."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
