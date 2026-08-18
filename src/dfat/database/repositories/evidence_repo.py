"""SQLAlchemy evidence repository implementing ``IEvidenceRepository``."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.core.interfaces.repository import IEvidenceRepository
from dfat.core.models.evidence import EvidenceImage
from dfat.database.exceptions import DatabaseError
from dfat.database.mappers import evidence_domain_to_orm, evidence_orm_to_domain
from dfat.database.models.evidence_orm import EvidenceRecordORM


class SQLAlchemyEvidenceRepository(IEvidenceRepository):
    """Async SQLAlchemy implementation of the evidence repository port."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the evidence repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def save(self, entity: EvidenceImage) -> str:  # type: ignore[override]
        """Persist evidence metadata and return its identifier."""
        orm = evidence_domain_to_orm(entity)
        async with self._session_factory() as session:
            try:
                merged = await session.merge(orm)
                await session.commit()
                return str(merged.id)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to save evidence",
                    context={"evidence_id": entity.evidence_id, "error": str(exc)},
                ) from exc

    async def get(self, entity_id: str) -> Optional[EvidenceImage]:  # type: ignore[override]
        """Load evidence metadata by identifier."""
        async with self._session_factory() as session:
            try:
                orm = await session.get(EvidenceRecordORM, entity_id)
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load evidence",
                    context={"evidence_id": entity_id, "error": str(exc)},
                ) from exc
            return evidence_orm_to_domain(orm) if orm is not None else None

    async def list_all(self) -> list[EvidenceImage]:  # type: ignore[override]
        """List all evidence metadata records."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(select(EvidenceRecordORM))
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list evidence",
                    context={"error": str(exc)},
                ) from exc
            return [evidence_orm_to_domain(row) for row in rows]

    async def delete(self, entity_id: str) -> bool:  # type: ignore[override]
        """Delete evidence metadata by identifier."""
        async with self._session_factory() as session:
            try:
                orm = await session.get(EvidenceRecordORM, entity_id)
                if orm is None:
                    return False
                await session.delete(orm)
                await session.commit()
                return True
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to delete evidence",
                    context={"evidence_id": entity_id, "error": str(exc)},
                ) from exc

    async def get_by_ids(self, evidence_ids: list[str]) -> dict[str, EvidenceImage]:
        """Batch-load evidence records keyed by identifier.

        Args:
            evidence_ids: Evidence identifiers to load.

        Returns:
            Mapping of evidence ID to domain record. Missing IDs are omitted.
        """
        unique_ids = list(dict.fromkeys(evidence_ids))
        if not unique_ids:
            return {}
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(EvidenceRecordORM).where(EvidenceRecordORM.id.in_(unique_ids))
                )
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load evidence by ids",
                    context={"evidence_ids": unique_ids, "error": str(exc)},
                ) from exc
            return {row.id: evidence_orm_to_domain(row) for row in rows}

    async def get_by_case(self, case_id: str) -> list[EvidenceImage]:
        """List evidence belonging to a case.

        Args:
            case_id: Case identifier.

        Returns:
            Matching evidence records.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(EvidenceRecordORM).where(EvidenceRecordORM.case_id == case_id)
                )
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list evidence by case",
                    context={"case_id": case_id, "error": str(exc)},
                ) from exc
            return [evidence_orm_to_domain(row) for row in rows]

    async def get_by_hash(self, hash_value: str) -> Optional[EvidenceImage]:
        """Load evidence by original integrity hash.

        Args:
            hash_value: Integrity hash digest.

        Returns:
            Matching evidence if found; otherwise ``None``.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(EvidenceRecordORM)
                    .where(EvidenceRecordORM.original_hash == hash_value)
                    .limit(1)
                )
                orm = result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load evidence by hash",
                    context={"hash": hash_value, "error": str(exc)},
                ) from exc
            return evidence_orm_to_domain(orm) if orm is not None else None
