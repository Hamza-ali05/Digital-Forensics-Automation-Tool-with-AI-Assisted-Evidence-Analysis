"""Insert-only chain-of-custody repository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.database.exceptions import DatabaseError
from dfat.database.mappers import custody_domain_to_orm, custody_orm_to_domain
from dfat.database.models.custody_orm import ChainOfCustodyORM
from dfat.evidence_management.models import ChainOfCustodyRecord


class CustodyRepository:
    """Append-only custody chain persistence (no update/delete API)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the custody repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def add_record(self, record: ChainOfCustodyRecord) -> str:
        """Insert a custody record with a sequential per-evidence entry number.

        Args:
            record: Domain custody record.

        Returns:
            Persisted custody record identifier.
        """
        async with self._session_factory() as session:
            try:
                entry_number = await self._next_entry_number(
                    session,
                    record.evidence_id,
                )
                orm = custody_domain_to_orm(record, entry_number=entry_number)
                session.add(orm)
                await session.commit()
                return str(orm.id)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to append custody record",
                    context={
                        "evidence_id": record.evidence_id,
                        "error": str(exc),
                    },
                ) from exc

    async def get_chain(self, evidence_id: str) -> list[ChainOfCustodyRecord]:
        """Return the ordered custody chain for an evidence item."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(ChainOfCustodyORM)
                    .where(ChainOfCustodyORM.evidence_id == evidence_id)
                    .order_by(ChainOfCustodyORM.entry_number.asc())
                )
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load custody chain",
                    context={"evidence_id": evidence_id, "error": str(exc)},
                ) from exc
            return [custody_orm_to_domain(row) for row in rows]

    async def get_latest(self, evidence_id: str) -> ChainOfCustodyRecord | None:
        """Return the latest custody record for an evidence item."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(ChainOfCustodyORM)
                    .where(ChainOfCustodyORM.evidence_id == evidence_id)
                    .order_by(ChainOfCustodyORM.entry_number.desc())
                    .limit(1)
                )
                orm = result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load latest custody record",
                    context={"evidence_id": evidence_id, "error": str(exc)},
                ) from exc
            return custody_orm_to_domain(orm) if orm is not None else None

    async def get_by_user(self, user_id: str) -> list[ChainOfCustodyRecord]:
        """List custody records performed by a user."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(ChainOfCustodyORM)
                    .where(ChainOfCustodyORM.performed_by_user_id == user_id)
                    .order_by(ChainOfCustodyORM.timestamp.asc())
                )
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list custody records by user",
                    context={"user_id": user_id, "error": str(exc)},
                ) from exc
            return [custody_orm_to_domain(row) for row in rows]

    async def count_by_evidence(self, evidence_id: str) -> int:
        """Return the number of custody records for an evidence item."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(func.count())
                    .select_from(ChainOfCustodyORM)
                    .where(ChainOfCustodyORM.evidence_id == evidence_id)
                )
                return int(result.scalar_one())
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to count custody records",
                    context={"evidence_id": evidence_id, "error": str(exc)},
                ) from exc

    async def _next_entry_number(
        self,
        session: AsyncSession,
        evidence_id: str,
    ) -> int:
        """Allocate the next sequential entry number for an evidence chain."""
        result = await session.execute(
            select(func.max(ChainOfCustodyORM.entry_number)).where(
                ChainOfCustodyORM.evidence_id == evidence_id
            )
        )
        current = result.scalar_one()
        return int(current or 0) + 1
