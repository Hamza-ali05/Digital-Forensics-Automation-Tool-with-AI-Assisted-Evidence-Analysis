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
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(ArtefactRecordORM).where(
                        ArtefactRecordORM.evidence_id == entity_id
                    )
                )
                rows = list(result.scalars().all())
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load artefact set",
                    context={"evidence_id": entity_id, "error": str(exc)},
                ) from exc
            if not rows:
                return None
            artefacts = [artefact_orm_to_domain(row) for row in rows]
            categories = sorted(
                {artefact.category for artefact in artefacts},
                key=lambda item: item.value,
            )
            return ArtefactSet(
                evidence_id=entity_id,
                artefacts=artefacts,
                categories_present=categories,
                extraction_timestamp=max(
                    (artefact.parsed_at for artefact in artefacts),
                    default=datetime.now(UTC),
                ),
            )

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
        grouped: dict[str, list[Artefact]] = {}
        for row in rows:
            grouped.setdefault(row.evidence_id, []).append(artefact_orm_to_domain(row))
        sets: list[ArtefactSet] = []
        for evidence_id, artefacts in grouped.items():
            categories = sorted(
                {artefact.category for artefact in artefacts},
                key=lambda item: item.value,
            )
            sets.append(
                ArtefactSet(
                    evidence_id=evidence_id,
                    artefacts=artefacts,
                    categories_present=categories,
                    extraction_timestamp=max(
                        (artefact.parsed_at for artefact in artefacts),
                        default=datetime.now(UTC),
                    ),
                )
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
