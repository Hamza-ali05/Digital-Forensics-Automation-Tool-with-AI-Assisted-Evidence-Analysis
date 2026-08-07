"""Evidence status history and metadata repositories."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.case_management.enums import EvidenceStatus
from dfat.database.exceptions import DatabaseError
from dfat.database.mappers import (
    evidence_metadata_domain_to_orm,
    evidence_metadata_orm_to_domain,
    evidence_status_domain_to_orm,
    evidence_status_orm_to_domain,
)
from dfat.database.models.evidence_orm import EvidenceRecordORM
from dfat.database.models.evidence_status_orm import (
    EvidenceMetadataORM,
    EvidenceStatusHistoryORM,
)
from dfat.evidence_management.models import (
    EvidenceMetadataRecord,
    EvidenceStatusChange,
    HashSet,
)


class EvidenceStatusRepository:
    """Append-only evidence status history persistence."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the evidence status repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def add_status_change(self, change: EvidenceStatusChange) -> str:
        """Insert a status-change record and update ``evidence_records.status``.

        Args:
            change: Domain status-change event.

        Returns:
            Persisted history row identifier.
        """
        orm = evidence_status_domain_to_orm(change)
        if not orm.id:
            orm.id = str(uuid4())
        async with self._session_factory() as session:
            try:
                session.add(orm)
                evidence = await session.get(EvidenceRecordORM, change.evidence_id)
                if evidence is not None:
                    evidence.status = change.new_status.value
                await session.commit()
                return str(orm.id)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to append evidence status change",
                    context={
                        "evidence_id": change.evidence_id,
                        "error": str(exc),
                    },
                ) from exc

    async def get_history(self, evidence_id: str) -> list[EvidenceStatusChange]:
        """Return ordered status history for an evidence item."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(EvidenceStatusHistoryORM)
                    .where(EvidenceStatusHistoryORM.evidence_id == evidence_id)
                    .order_by(EvidenceStatusHistoryORM.changed_at.asc())
                )
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load evidence status history",
                    context={"evidence_id": evidence_id, "error": str(exc)},
                ) from exc
            return [evidence_status_orm_to_domain(row) for row in rows]

    async def get_current_status(self, evidence_id: str) -> Optional[EvidenceStatus]:
        """Return the latest status for an evidence item.

        Prefers the latest history row; falls back to ``evidence_records.status``.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(EvidenceStatusHistoryORM)
                    .where(EvidenceStatusHistoryORM.evidence_id == evidence_id)
                    .order_by(
                        EvidenceStatusHistoryORM.changed_at.desc(),
                        EvidenceStatusHistoryORM.id.desc(),
                    )
                    .limit(1)
                )
                row = result.scalar_one_or_none()
                if row is not None:
                    return EvidenceStatus(row.new_status)
                evidence = await session.get(EvidenceRecordORM, evidence_id)
                if evidence is not None and evidence.status:
                    return EvidenceStatus(evidence.status)
                return None
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to read current evidence status",
                    context={"evidence_id": evidence_id, "error": str(exc)},
                ) from exc

    async def get_by_status(self, status: EvidenceStatus) -> list[str]:
        """Return evidence IDs currently in the given status."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(EvidenceRecordORM.id).where(
                        EvidenceRecordORM.status == status.value
                    )
                )
                return [str(row[0]) for row in result.all()]
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list evidence by status",
                    context={"status": status.value, "error": str(exc)},
                ) from exc


class EvidenceMetadataRepository:
    """Evidence metadata and multi-algorithm hash persistence."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the evidence metadata repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def save_metadata(self, metadata: EvidenceMetadataRecord) -> str:
        """Upsert evidence metadata and mirror hash digests onto evidence_records.

        Args:
            metadata: Domain metadata record.

        Returns:
            Persisted metadata row identifier.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(EvidenceMetadataORM).where(
                        EvidenceMetadataORM.evidence_id == metadata.evidence_id
                    )
                )
                existing = result.scalar_one_or_none()
                orm = evidence_metadata_domain_to_orm(metadata)
                if existing is not None:
                    orm.id = existing.id
                    merged = await session.merge(orm)
                    row_id = str(merged.id)
                else:
                    if not orm.id:
                        orm.id = str(uuid4())
                    session.add(orm)
                    row_id = str(orm.id)

                evidence = await session.get(EvidenceRecordORM, metadata.evidence_id)
                if evidence is not None:
                    evidence.hash_md5 = metadata.hash_set.md5
                    evidence.hash_sha1 = metadata.hash_set.sha1
                    if not evidence.original_hash:
                        evidence.original_hash = metadata.hash_set.sha256

                await session.commit()
                return row_id
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to save evidence metadata",
                    context={
                        "evidence_id": metadata.evidence_id,
                        "error": str(exc),
                    },
                ) from exc

    async def get_metadata(
        self,
        evidence_id: str,
    ) -> Optional[EvidenceMetadataRecord]:
        """Load metadata for an evidence item."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(EvidenceMetadataORM)
                    .where(EvidenceMetadataORM.evidence_id == evidence_id)
                    .limit(1)
                )
                orm = result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load evidence metadata",
                    context={"evidence_id": evidence_id, "error": str(exc)},
                ) from exc
            return evidence_metadata_orm_to_domain(orm) if orm is not None else None

    async def get_by_mime_type(
        self,
        mime_type: str,
    ) -> list[EvidenceMetadataRecord]:
        """List metadata rows matching a MIME type."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(EvidenceMetadataORM).where(
                        EvidenceMetadataORM.mime_type == mime_type
                    )
                )
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list metadata by MIME type",
                    context={"mime_type": mime_type, "error": str(exc)},
                ) from exc
            return [evidence_metadata_orm_to_domain(row) for row in rows]

    async def get_hash_set(self, evidence_id: str) -> Optional[HashSet]:
        """Return the multi-algorithm hash set for an evidence item."""
        metadata = await self.get_metadata(evidence_id)
        return metadata.hash_set if metadata is not None else None
