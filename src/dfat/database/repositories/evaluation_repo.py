"""SQLAlchemy repositories for benchmark and usability evaluation."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.database.exceptions import DatabaseError
from dfat.database.mappers import (
    benchmark_domain_to_orm,
    benchmark_orm_to_domain,
    usability_domain_to_orm,
    usability_orm_to_domain,
)
from dfat.database.models.evaluation_orm import BenchmarkRecordORM, UsabilityRecordORM
from dfat.database.repositories.base_repo import SQLAlchemyRepository


class SQLAlchemyBenchmarkRepository(
    SQLAlchemyRepository[BenchmarkResult, BenchmarkRecordORM]
):
    """Benchmark result persistence."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the benchmark repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        super().__init__(
            session_factory=session_factory,
            orm_class=BenchmarkRecordORM,
            to_domain=benchmark_orm_to_domain,
            to_orm=benchmark_domain_to_orm,
        )

    async def get_by_dataset(self, dataset_name: str) -> list[BenchmarkResult]:
        """List benchmark results for a dataset name.

        Args:
            dataset_name: Ground-truth dataset name.

        Returns:
            Matching benchmark results.
        """
        return await self.list_by_field("dataset_name", dataset_name)

    async def get_latest(self, dataset_name: str) -> Optional[BenchmarkResult]:
        """Return the most recent benchmark result for a dataset.

        Args:
            dataset_name: Ground-truth dataset name.

        Returns:
            Latest result if present; otherwise ``None``.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(BenchmarkRecordORM)
                    .where(BenchmarkRecordORM.dataset_name == dataset_name)
                    .order_by(BenchmarkRecordORM.evaluated_at.desc())
                    .limit(1)
                )
                orm = result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load latest benchmark",
                    context={"dataset_name": dataset_name, "error": str(exc)},
                ) from exc
            return benchmark_orm_to_domain(orm) if orm is not None else None


class SQLAlchemyUsabilityRepository(
    SQLAlchemyRepository[UsabilityResponse, UsabilityRecordORM]
):
    """Usability questionnaire response persistence."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the usability repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        super().__init__(
            session_factory=session_factory,
            orm_class=UsabilityRecordORM,
            to_domain=usability_orm_to_domain,
            to_orm=usability_domain_to_orm,
        )

    async def get_all_responses(self) -> list[UsabilityResponse]:
        """Return all usability responses."""
        return await self.list_all()

    async def count_responses(self) -> int:
        """Return the number of stored usability responses."""
        return await self.count()

    async def delete_all_responses(self) -> int:
        """Delete all usability responses (ethics data destruction).

        Returns:
            Number of rows deleted.

        Raises:
            DatabaseError: If the delete fails.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(delete(UsabilityRecordORM))
                await session.commit()
                return int(result.rowcount or 0)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to delete usability responses",
                    context={"error": str(exc)},
                ) from exc
