"""SQLAlchemy dataset registry repository."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.dataset_intelligence.enums import DatasetCategory, DatasetStatus
from dfat.dataset_intelligence.models import DatasetRecord
from dfat.database.exceptions import DatabaseError
from dfat.database.mappers import dataset_domain_to_orm, dataset_orm_to_domain
from dfat.database.models.dataset_orm import DatasetRecordORM


class DatasetRepository:
    """Async SQLAlchemy persistence for dataset registry records."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, dataset: DatasetRecord) -> str:
        orm = dataset_domain_to_orm(dataset)
        async with self._session_factory() as session:
            try:
                existing = await self._load_existing(session, dataset)
                if existing is not None:
                    orm.id = existing.id
                merged = await session.merge(orm)
                await session.commit()
                return str(merged.dataset_id)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to save dataset record",
                    context={"dataset_id": dataset.dataset_id, "error": str(exc)},
                ) from exc

    async def get(self, dataset_id: str) -> Optional[DatasetRecord]:
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(DatasetRecordORM)
                    .where(DatasetRecordORM.dataset_id == dataset_id)
                    .limit(1)
                )
                orm = result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load dataset record",
                    context={"dataset_id": dataset_id, "error": str(exc)},
                ) from exc
            if orm is None:
                return None
            return dataset_orm_to_domain(orm)

    async def list_datasets(
        self,
        *,
        category: Optional[DatasetCategory] = None,
        status: Optional[DatasetStatus] = None,
        include_deleted: bool = False,
    ) -> list[DatasetRecord]:
        async with self._session_factory() as session:
            try:
                stmt = select(DatasetRecordORM)
                if category is not None:
                    stmt = stmt.where(DatasetRecordORM.category == category.value)
                if status is not None:
                    stmt = stmt.where(DatasetRecordORM.status == status.value)
                if not include_deleted:
                    stmt = stmt.where(DatasetRecordORM.is_deleted.is_(False))
                stmt = stmt.order_by(DatasetRecordORM.discovered_at.desc())
                result = await session.execute(stmt)
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list dataset records",
                    context={"error": str(exc)},
                ) from exc
            return [dataset_orm_to_domain(row) for row in rows]

    async def get_by_hash(self, hash_sha256: str) -> Optional[DatasetRecord]:
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(DatasetRecordORM)
                    .where(DatasetRecordORM.hash_sha256 == hash_sha256)
                    .where(DatasetRecordORM.is_deleted.is_(False))
                    .limit(1)
                )
                orm = result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load dataset by hash",
                    context={"hash_sha256": hash_sha256, "error": str(exc)},
                ) from exc
            return dataset_orm_to_domain(orm) if orm is not None else None

    async def get_by_path(self, file_path: Path | str) -> Optional[DatasetRecord]:
        path_str = str(file_path)
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(DatasetRecordORM)
                    .where(DatasetRecordORM.file_path == path_str)
                    .where(DatasetRecordORM.is_deleted.is_(False))
                    .limit(1)
                )
                orm = result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load dataset by path",
                    context={"file_path": path_str, "error": str(exc)},
                ) from exc
            return dataset_orm_to_domain(orm) if orm is not None else None

    async def soft_delete(self, dataset_id: str) -> bool:
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(DatasetRecordORM)
                    .where(DatasetRecordORM.dataset_id == dataset_id)
                    .limit(1)
                )
                orm = result.scalar_one_or_none()
                if orm is None:
                    return False
                orm.is_deleted = True
                orm.deleted_at = datetime.now(UTC)
                orm.status = DatasetStatus.ARCHIVED.value
                await session.commit()
                return True
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to soft-delete dataset",
                    context={"dataset_id": dataset_id, "error": str(exc)},
                ) from exc

    async def update_file_timestamps(
        self,
        dataset_id: str,
        *,
        last_seen_at: Optional[datetime],
        file_modified_at: Optional[datetime],
    ) -> bool:
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(DatasetRecordORM)
                    .where(DatasetRecordORM.dataset_id == dataset_id)
                    .limit(1)
                )
                orm = result.scalar_one_or_none()
                if orm is None:
                    return False
                orm.last_seen_at = last_seen_at
                orm.file_modified_at = file_modified_at
                await session.commit()
                return True
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to update dataset timestamps",
                    context={"dataset_id": dataset_id, "error": str(exc)},
                ) from exc

    async def get_statistics(self) -> dict[str, object]:
        datasets = await self.list_datasets()
        category_counts: dict[str, int] = {}
        format_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        total_size_bytes = 0

        for dataset in datasets:
            category_counts[dataset.category.value] = (
                category_counts.get(dataset.category.value, 0) + 1
            )
            format_counts[dataset.format.value] = (
                format_counts.get(dataset.format.value, 0) + 1
            )
            status_counts[dataset.status.value] = (
                status_counts.get(dataset.status.value, 0) + 1
            )
            total_size_bytes += dataset.file_size_bytes

        return {
            "total_count": len(datasets),
            "category_counts": category_counts,
            "format_counts": format_counts,
            "status_counts": status_counts,
            "total_size_bytes": total_size_bytes,
        }

    async def _load_existing(
        self,
        session: AsyncSession,
        dataset: DatasetRecord,
    ) -> Optional[DatasetRecordORM]:
        result = await session.execute(
            select(DatasetRecordORM)
            .where(
                (DatasetRecordORM.dataset_id == dataset.dataset_id)
                | (DatasetRecordORM.file_path == str(dataset.file_path))
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
