"""Insert-only SQLAlchemy audit log repository."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.core.enums import PipelineStage
from dfat.core.models.pipeline import AuditEntry
from dfat.database.exceptions import DatabaseError
from dfat.database.mappers import audit_domain_to_orm, audit_orm_to_domain
from dfat.database.models.audit_orm import AuditLogRecordORM


class SQLAlchemyAuditRepository:
    """Append-only audit trail persistence (no update/delete API)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the audit repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def log_entry(
        self,
        entry: AuditEntry,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> str:
        """Insert an audit entry (append-only).

        Args:
            entry: Domain audit entry.
            user_id: Optional acting user ID.
            ip_address: Optional client IP.

        Returns:
            Persisted audit row identifier.
        """
        orm = audit_domain_to_orm(entry, user_id=user_id, ip_address=ip_address)
        if not orm.id:
            orm.id = str(uuid4())
        async with self._session_factory() as session:
            try:
                session.add(orm)
                await session.commit()
                return str(orm.id)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to append audit entry",
                    context={"entry_number": entry.entry_number, "error": str(exc)},
                ) from exc

    async def get_by_evidence(self, evidence_id: str) -> list[AuditEntry]:
        """List audit entries for an evidence ID."""
        return await self._list_where(AuditLogRecordORM.evidence_id == evidence_id)

    async def get_by_user(self, user_id: str) -> list[AuditEntry]:
        """List audit entries for a user ID."""
        return await self._list_where(AuditLogRecordORM.user_id == user_id)

    async def get_by_stage(self, stage: PipelineStage) -> list[AuditEntry]:
        """List audit entries for a pipeline stage."""
        return await self._list_where(AuditLogRecordORM.stage == stage.value)

    async def get_by_date_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[AuditEntry]:
        """List audit entries within an inclusive timestamp range."""
        return await self._list_where(
            AuditLogRecordORM.timestamp >= start,
            AuditLogRecordORM.timestamp <= end,
        )

    async def get_latest_entry_number(self) -> int:
        """Return the highest audit entry number, or ``0`` when empty."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(func.max(AuditLogRecordORM.entry_number))
                )
                value = result.scalar_one()
                return int(value or 0)
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to read latest audit entry number",
                    context={"error": str(exc)},
                ) from exc

    async def _list_where(self, *clauses: object) -> list[AuditEntry]:
        """Execute a filtered audit query ordered by entry number."""
        async with self._session_factory() as session:
            try:
                stmt = select(AuditLogRecordORM).order_by(AuditLogRecordORM.entry_number)
                for clause in clauses:
                    stmt = stmt.where(clause)  # type: ignore[arg-type]
                result = await session.execute(stmt)
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to query audit log",
                    context={"error": str(exc)},
                ) from exc
            return [audit_orm_to_domain(row) for row in rows]
