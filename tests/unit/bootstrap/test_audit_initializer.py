"""Unit tests for AuditInitializer."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from dfat.bootstrap.audit_initializer import AuditInitializer
from dfat.bootstrap.models import InitPhase, InitStatus
from dfat.database.engine import DatabaseEngine
from dfat.database.models.audit_orm import AuditLogRecordORM
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.services.audit_service import AuditService
from dfat.settings import load_settings


def _audit_initializer(
    engine: DatabaseEngine,
    audit_log_path: Path,
) -> AuditInitializer:
    settings = load_settings(env="development")
    settings.logging.audit_log_path = audit_log_path
    audit_repo = SQLAlchemyAuditRepository(engine.session_factory)
    file_logger = ForensicAuditLogger(audit_log_path=audit_log_path)
    audit_service = AuditService(audit_repo=audit_repo, forensic_audit_logger=file_logger)
    return AuditInitializer(audit_service=audit_service, settings=settings)


@pytest.mark.asyncio
async def test_audit_log_write_probe_succeeds(tmp_path: Path) -> None:
    audit_log = tmp_path / "audit.log"
    engine = DatabaseEngine(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'audit.db').as_posix()}",
        echo=False,
    )
    try:
        await engine.create_tables()
        initializer = _audit_initializer(engine, audit_log)
        assert initializer._verify_audit_log_writable(audit_log) is True
        assert not any(tmp_path.glob(".dfat_audit_write_test_*"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_initialize_logs_startup_audit_entry(tmp_path: Path) -> None:
    audit_log = tmp_path / "outputs" / "audit.log"
    engine = DatabaseEngine(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'audit.db').as_posix()}",
        echo=False,
    )
    try:
        await engine.create_tables()
        initializer = _audit_initializer(engine, audit_log)
        result = await initializer.initialize()

        assert result.phase == InitPhase.AUDIT_LOGGING
        assert result.status == InitStatus.COMPLETED
        assert result.details["audit_log_writable"] is True
        assert result.details["database_audit_accessible"] is True
        assert result.details["dual_logging_verified"] is True
        assert result.details["startup_audit_logged"] is True
        assert result.details["startup_file_logged"] is True

        async with engine.session_factory() as session:
            rows = (
                await session.execute(
                    select(AuditLogRecordORM).where(
                        AuditLogRecordORM.action == "SYSTEM_STARTUP"
                    )
                )
            ).scalars().all()
        assert len(rows) >= 1

        file_entries = initializer._audit_service._file_logger.get_audit_trail("system")
        assert any(entry.action == "SYSTEM_STARTUP" for entry in file_entries)
        assert audit_log.exists()
    finally:
        await engine.dispose()
