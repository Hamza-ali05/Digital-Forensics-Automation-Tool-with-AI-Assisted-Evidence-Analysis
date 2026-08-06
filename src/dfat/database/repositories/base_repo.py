"""Generic async SQLAlchemy repository base."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generic, Optional, TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.database.base import Base
from dfat.database.exceptions import DatabaseError

T = TypeVar("T")
OrmT = TypeVar("OrmT", bound=Base)


class SQLAlchemyRepository(Generic[T, OrmT]):
    """Generic async CRUD repository using ORM ↔ domain mappers."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        orm_class: type[OrmT],
        to_domain: Callable[[OrmT], T],
        to_orm: Callable[[T], OrmT],
    ) -> None:
        """Initialise the repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
            orm_class: ORM mapped class.
            to_domain: Mapper from ORM row to domain entity.
            to_orm: Mapper from domain entity to ORM row.
        """
        self._session_factory = session_factory
        self._orm_class = orm_class
        self._to_domain = to_domain
        self._to_orm = to_orm

    async def save(self, entity: T) -> str:
        """Persist an entity and return its identifier.

        Args:
            entity: Domain entity to store.

        Returns:
            Persisted entity identifier.

        Raises:
            DatabaseError: If the persistence operation fails.
        """
        orm = self._to_orm(entity)
        async with self._session_factory() as session:
            try:
                merged = await session.merge(orm)
                await session.commit()
                return str(merged.id)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to save entity",
                    context={"orm_class": self._orm_class.__name__, "error": str(exc)},
                ) from exc

    async def get(self, entity_id: str) -> Optional[T]:
        """Retrieve an entity by identifier.

        Args:
            entity_id: Entity identifier.

        Returns:
            Domain entity if found; otherwise ``None``.

        Raises:
            DatabaseError: If the query fails.
        """
        async with self._session_factory() as session:
            try:
                orm = await session.get(self._orm_class, entity_id)
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load entity",
                    context={"entity_id": entity_id, "error": str(exc)},
                ) from exc
            if orm is None:
                return None
            return self._to_domain(orm)

    async def list_all(self) -> list[T]:
        """List all persisted entities.

        Returns:
            List of domain entities.

        Raises:
            DatabaseError: If the query fails.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(select(self._orm_class))
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list entities",
                    context={"orm_class": self._orm_class.__name__, "error": str(exc)},
                ) from exc
            return [self._to_domain(row) for row in rows]

    async def delete(self, entity_id: str) -> bool:
        """Delete an entity by identifier.

        Args:
            entity_id: Entity identifier.

        Returns:
            ``True`` if a row was deleted; otherwise ``False``.

        Raises:
            DatabaseError: If the delete fails.
        """
        async with self._session_factory() as session:
            try:
                orm = await session.get(self._orm_class, entity_id)
                if orm is None:
                    return False
                await session.delete(orm)
                await session.commit()
                return True
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to delete entity",
                    context={"entity_id": entity_id, "error": str(exc)},
                ) from exc

    async def get_by_field(self, field_name: str, value: Any) -> Optional[T]:
        """Load the first entity matching a column value.

        Args:
            field_name: ORM attribute name.
            value: Value to match.

        Returns:
            Domain entity if found; otherwise ``None``.

        Raises:
            DatabaseError: If the field is invalid or the query fails.
        """
        column = getattr(self._orm_class, field_name, None)
        if column is None:
            raise DatabaseError(
                f"Unknown field '{field_name}' on {self._orm_class.__name__}",
                context={"field_name": field_name},
            )
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(self._orm_class).where(column == value).limit(1)
                )
                orm = result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to query by field",
                    context={"field_name": field_name, "error": str(exc)},
                ) from exc
            return self._to_domain(orm) if orm is not None else None

    async def list_by_field(self, field_name: str, value: Any) -> list[T]:
        """List entities matching a column value.

        Args:
            field_name: ORM attribute name.
            value: Value to match.

        Returns:
            Matching domain entities.

        Raises:
            DatabaseError: If the field is invalid or the query fails.
        """
        column = getattr(self._orm_class, field_name, None)
        if column is None:
            raise DatabaseError(
                f"Unknown field '{field_name}' on {self._orm_class.__name__}",
                context={"field_name": field_name},
            )
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(self._orm_class).where(column == value)
                )
                rows = result.scalars().all()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list by field",
                    context={"field_name": field_name, "error": str(exc)},
                ) from exc
            return [self._to_domain(row) for row in rows]

    async def count(self) -> int:
        """Return the number of persisted rows.

        Returns:
            Row count.

        Raises:
            DatabaseError: If the count query fails.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(func.count()).select_from(self._orm_class)
                )
                return int(result.scalar_one())
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to count entities",
                    context={"orm_class": self._orm_class.__name__, "error": str(exc)},
                ) from exc
