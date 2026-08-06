"""SQLAlchemy user account repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from dfat.database.exceptions import DatabaseError
from dfat.database.models.user import RoleORM, UserORM
from dfat.database.repositories.base_repo import SQLAlchemyRepository


class SQLAlchemyUserRepository(SQLAlchemyRepository[UserORM, UserORM]):
    """User persistence with lockout and login-attempt helpers."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the user repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        super().__init__(
            session_factory=session_factory,
            orm_class=UserORM,
            to_domain=lambda orm: orm,
            to_orm=lambda entity: entity,
        )

    async def get_by_username(self, username: str) -> Optional[UserORM]:
        """Load a user by username.

        Args:
            username: Unique username.

        Returns:
            ``UserORM`` if found; otherwise ``None``.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(UserORM)
                    .options(selectinload(UserORM.role))
                    .where(UserORM.username == username)
                    .limit(1)
                )
                return result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load user by username",
                    context={"username": username, "error": str(exc)},
                ) from exc

    async def get_by_email(self, email: str) -> Optional[UserORM]:
        """Load a user by email.

        Args:
            email: Unique email address.

        Returns:
            ``UserORM`` if found; otherwise ``None``.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(UserORM)
                    .options(selectinload(UserORM.role))
                    .where(UserORM.email == email)
                    .limit(1)
                )
                return result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load user by email",
                    context={"email": email, "error": str(exc)},
                ) from exc

    async def get_role_by_name(self, role_name: str) -> Optional[RoleORM]:
        """Load a role by name.

        Args:
            role_name: Role name (e.g. ``analyst``).

        Returns:
            ``RoleORM`` if found; otherwise ``None``.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(RoleORM).where(RoleORM.name == role_name).limit(1)
                )
                return result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load role by name",
                    context={"role_name": role_name, "error": str(exc)},
                ) from exc

    async def get(self, entity_id: str) -> Optional[UserORM]:
        """Load a user by ID with role relationship."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(UserORM)
                    .options(selectinload(UserORM.role))
                    .where(UserORM.id == entity_id)
                    .limit(1)
                )
                return result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load user",
                    context={"user_id": entity_id, "error": str(exc)},
                ) from exc

    async def list_all(self) -> list[UserORM]:
        """List all users with roles loaded."""
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(UserORM).options(selectinload(UserORM.role))
                )
                return list(result.scalars().all())
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list users",
                    context={"error": str(exc)},
                ) from exc

    async def increment_failed_attempts(self, user_id: str) -> None:
        """Increment the failed login attempt counter.

        Args:
            user_id: User identifier.
        """
        async with self._session_factory() as session:
            try:
                await session.execute(
                    update(UserORM)
                    .where(UserORM.id == user_id)
                    .values(failed_login_attempts=UserORM.failed_login_attempts + 1)
                )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to increment login attempts",
                    context={"user_id": user_id, "error": str(exc)},
                ) from exc

    async def reset_failed_attempts(self, user_id: str) -> None:
        """Reset failed login attempts to zero.

        Args:
            user_id: User identifier.
        """
        async with self._session_factory() as session:
            try:
                await session.execute(
                    update(UserORM)
                    .where(UserORM.id == user_id)
                    .values(failed_login_attempts=0)
                )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to reset login attempts",
                    context={"user_id": user_id, "error": str(exc)},
                ) from exc

    async def lock_user(self, user_id: str, until: datetime) -> None:
        """Lock a user account until a given timestamp.

        Args:
            user_id: User identifier.
            until: Lock expiry timestamp.
        """
        async with self._session_factory() as session:
            try:
                await session.execute(
                    update(UserORM)
                    .where(UserORM.id == user_id)
                    .values(is_locked=True, locked_until=until)
                )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to lock user",
                    context={"user_id": user_id, "error": str(exc)},
                ) from exc

    async def unlock_user(self, user_id: str) -> None:
        """Unlock a user account and clear lock metadata.

        Args:
            user_id: User identifier.
        """
        async with self._session_factory() as session:
            try:
                await session.execute(
                    update(UserORM)
                    .where(UserORM.id == user_id)
                    .values(
                        is_locked=False,
                        locked_until=None,
                        failed_login_attempts=0,
                    )
                )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to unlock user",
                    context={"user_id": user_id, "error": str(exc)},
                ) from exc

    async def update_last_login(self, user_id: str) -> None:
        """Record the current UTC time as the user's last login.

        Args:
            user_id: User identifier.
        """
        async with self._session_factory() as session:
            try:
                await session.execute(
                    update(UserORM)
                    .where(UserORM.id == user_id)
                    .values(last_login=datetime.now(UTC))
                )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to update last login",
                    context={"user_id": user_id, "error": str(exc)},
                ) from exc
