"""SQLAlchemy artefact repository implementing ``IArtefactRepository``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.core.enums import ArtefactCategory
from dfat.core.interfaces.repository import IArtefactRepository
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.database.exceptions import DatabaseError
from dfat.database.mappers import artefact_domain_to_orm, artefact_orm_to_domain
from dfat.database.models.artefact_orm import ArtefactRecordORM


class SQLAlchemyArtefactRepository(IArtefactRepository):
    """Async SQLAlchemy implementation of the artefact-set repository port."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the artefact repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def save(self, entity: ArtefactSet) -> str:  # type: ignore[override]
        """Persist all artefacts in the set as individual rows."""
        async with self._session_factory() as session:
            try:
                await session.execute(
                    delete(ArtefactRecordORM).where(
                        ArtefactRecordORM.evidence_id == entity.evidence_id
                    )
                )
                for artefact in entity.artefacts:
                    orm = artefact_domain_to_orm(artefact, entity.evidence_id)
                    session.add(orm)
                await session.commit()
                return entity.evidence_id
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to save artefact set",
                    context={"evidence_id": entity.evidence_id, "error": str(exc)},
                ) from exc

    async def get(self, entity_id: str) -> Optional[ArtefactSet]:  # type: ignore[override]
        """Load all artefacts for an evidence ID into an ``ArtefactSet``."""
        sets = await self.get_by_evidence_ids([entity_id])
        return sets.get(entity_id)

    async def get_by_evidence_ids(
        self,
        evidence_ids: list[str],
    ) -> dict[str, ArtefactSet]:
        """Batch-load artefact sets keyed by evidence identifier.

        Args:
            evidence_ids: Evidence identifiers to load.

        Returns:
            Mapping of evidence ID to artefact set. Missing IDs are omitted.
        """
        unique_ids = list(dict.fromkeys(evidence_ids))
        if not unique_ids:
            return {}
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(ArtefactRecordORM).where(
                        ArtefactRecordORM.evidence_id.in_(unique_ids)
                    )
                )
                rows = list(result.scalars().all())
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load artefact sets by evidence ids",
                    context={"evidence_ids": unique_ids, "error": str(exc)},
                ) from exc
        return self._sets_from_rows(rows)

    async def list_all(self) -> list[ArtefactSet]:  # type: ignore[override]
        """List artefact sets grouped by evidence ID."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(select(ArtefactRecordORM))
                rows = list(result.scalars().all())
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list artefact sets",
                    context={"error": str(exc)},
                ) from exc
        return list(self._sets_from_rows(rows).values())

    @staticmethod
    def _sets_from_rows(rows: list[ArtefactRecordORM]) -> dict[str, ArtefactSet]:
        """Group ORM artefact rows into domain ``ArtefactSet`` values."""
        grouped: dict[str, list[Artefact]] = {}
        for row in rows:
            grouped.setdefault(row.evidence_id, []).append(artefact_orm_to_domain(row))
        sets: dict[str, ArtefactSet] = {}
        for evidence_id, artefacts in grouped.items():
            categories = sorted(
                {artefact.category for artefact in artefacts},
                key=lambda item: item.value,
            )
            sets[evidence_id] = ArtefactSet(
                evidence_id=evidence_id,
                artefacts=artefacts,
                categories_present=categories,
                extraction_timestamp=max(
                    (artefact.parsed_at for artefact in artefacts),
                    default=datetime.now(UTC),
                ),
            )
        return sets

    async def delete(self, entity_id: str) -> bool:  # type: ignore[override]
        """Delete all artefacts for an evidence ID."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    delete(ArtefactRecordORM).where(
                        ArtefactRecordORM.evidence_id == entity_id
                    )
                )
                await session.commit()
                return bool(result.rowcount)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to delete artefact set",
                    context={"evidence_id": entity_id, "error": str(exc)},
                ) from exc

    async def get_by_artefact_id(self, artefact_id: str) -> Optional[Artefact]:
        """Load a single artefact by its primary key.

        Args:
            artefact_id: Artefact record identifier.

        Returns:
            Domain artefact when found; otherwise ``None``.
        """
        async with self._session_factory() as session:
            try:
                row = await session.get(ArtefactRecordORM, artefact_id)
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load artefact by id",
                    context={"artefact_id": artefact_id, "error": str(exc)},
                ) from exc
            if row is None:
                return None
            return artefact_orm_to_domain(row)

    async def get_by_category(
        self,
        evidence_id: str,
        category: ArtefactCategory,
    ) -> list[Artefact]:
        """List artefacts for an evidence ID filtered by category.

        Args:
            evidence_id: Parent evidence identifier.
            category: Artefact category filter.

        Returns:
            Matching artefacts.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(ArtefactRecordORM).where(
                        ArtefactRecordORM.evidence_id == evidence_id,
                        ArtefactRecordORM.category == category.value,
                    )
                )
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list artefacts by category",
                    context={
                        "evidence_id": evidence_id,
                        "category": category.value,
                        "error": str(exc),
                    },
                ) from exc
            return [artefact_orm_to_domain(row) for row in rows]

    async def count_by_evidence(self, evidence_id: str) -> int:
        """Count artefacts stored for an evidence ID.

        Args:
            evidence_id: Parent evidence identifier.

        Returns:
            Artefact count.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(func.count())
                    .select_from(ArtefactRecordORM)
                    .where(ArtefactRecordORM.evidence_id == evidence_id)
                )
                return int(result.scalar_one())
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to count artefacts",
                    context={"evidence_id": evidence_id, "error": str(exc)},
                ) from exc
