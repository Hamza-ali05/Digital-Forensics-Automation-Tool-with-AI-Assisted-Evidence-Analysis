"""SQLAlchemy report repository implementing ``IReportRepository``."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.core.interfaces.repository import IReportRepository
from dfat.core.models.report import ForensicReport
from dfat.database.exceptions import DatabaseError
from dfat.database.mappers import report_domain_to_orm, report_orm_to_domain
from dfat.database.models.report_orm import ReportRecordORM


class SQLAlchemyReportRepository(IReportRepository):
    """Async SQLAlchemy implementation of the report repository port."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the report repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def save(self, entity: ForensicReport) -> str:  # type: ignore[override]
        """Persist a forensic report and return its identifier."""
        orm = report_domain_to_orm(entity)
        async with self._session_factory() as session:
            try:
                merged = await session.merge(orm)
                await session.commit()
                return str(merged.id)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to save report",
                    context={"report_id": entity.report_id, "error": str(exc)},
                ) from exc

    async def get(self, entity_id: str) -> Optional[ForensicReport]:  # type: ignore[override]
        """Load a forensic report by identifier."""
        async with self._session_factory() as session:
            try:
                orm = await session.get(ReportRecordORM, entity_id)
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load report",
                    context={"report_id": entity_id, "error": str(exc)},
                ) from exc
            return report_orm_to_domain(orm) if orm is not None else None

    async def list_all(self) -> list[ForensicReport]:  # type: ignore[override]
        """List all forensic reports."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(select(ReportRecordORM))
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list reports",
                    context={"error": str(exc)},
                ) from exc
            return [report_orm_to_domain(row) for row in rows]

    async def delete(self, entity_id: str) -> bool:  # type: ignore[override]
        """Delete a forensic report by identifier."""
        async with self._session_factory() as session:
            try:
                orm = await session.get(ReportRecordORM, entity_id)
                if orm is None:
                    return False
                await session.delete(orm)
                await session.commit()
                return True
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to delete report",
                    context={"report_id": entity_id, "error": str(exc)},
                ) from exc

    async def get_by_case(self, case_id: str) -> list[ForensicReport]:
        """List reports for a case.

        Args:
            case_id: Case identifier.

        Returns:
            Matching forensic reports.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(ReportRecordORM).where(ReportRecordORM.case_id == case_id)
                )
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list reports by case",
                    context={"case_id": case_id, "error": str(exc)},
                ) from exc
            return [report_orm_to_domain(row) for row in rows]

    async def get_by_evidence(self, evidence_id: str) -> Optional[ForensicReport]:
        """Load the latest report for an evidence ID.

        Args:
            evidence_id: Evidence identifier.

        Returns:
            Forensic report if found; otherwise ``None``.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(ReportRecordORM)
                    .where(ReportRecordORM.evidence_id == evidence_id)
                    .order_by(ReportRecordORM.created_at.desc())
                    .limit(1)
                )
                orm = result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load report by evidence",
                    context={"evidence_id": evidence_id, "error": str(exc)},
                ) from exc
            return report_orm_to_domain(orm) if orm is not None else None
