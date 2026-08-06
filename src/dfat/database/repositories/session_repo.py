"""SQLAlchemy user session repository for JWT revocation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import and_, delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.database.exceptions import DatabaseError
from dfat.database.models.session_orm import SessionORM


class SessionRepository:
    """Persist and revoke user JWT sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the session repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def create_session(
        self,
        user_id: str,
        token_jti: str,
        expires_at: datetime,
        ip_address: str,
        user_agent: str,
    ) -> SessionORM:
        """Create a persisted session row.

        Args:
            user_id: Owning user identifier.
            token_jti: JWT ID claim.
            expires_at: Session expiry timestamp.
            ip_address: Client IP address.
            user_agent: Client user-agent string.

        Returns:
            Persisted ``SessionORM``.
        """
        orm = SessionORM(
            id=str(uuid4()),
            user_id=user_id,
            token_jti=token_jti,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
            is_revoked=False,
        )
        async with self._session_factory() as session:
            try:
                session.add(orm)
                await session.commit()
                await session.refresh(orm)
                return orm
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to create session",
                    context={"user_id": user_id, "jti": token_jti, "error": str(exc)},
                ) from exc

    async def get_by_jti(self, jti: str) -> Optional[SessionORM]:
        """Load a session by JWT ID.

        Args:
            jti: JWT ID claim.

        Returns:
            Session if found; otherwise ``None``.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    select(SessionORM).where(SessionORM.token_jti == jti).limit(1)
                )
                return result.scalar_one_or_none()
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load session by JTI",
                    context={"jti": jti, "error": str(exc)},
                ) from exc

    async def revoke_session(self, jti: str) -> bool:
        """Revoke a single session by JWT ID.

        Args:
            jti: JWT ID claim.

        Returns:
            ``True`` if a session was revoked.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    update(SessionORM)
                    .where(SessionORM.token_jti == jti, SessionORM.is_revoked.is_(False))
                    .values(is_revoked=True, revoked_at=datetime.now(UTC))
                )
                await session.commit()
                return bool(result.rowcount)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to revoke session",
                    context={"jti": jti, "error": str(exc)},
                ) from exc

    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke all active sessions for a user.

        Args:
            user_id: User identifier.

        Returns:
            Number of sessions revoked.
        """
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    update(SessionORM)
                    .where(
                        SessionORM.user_id == user_id,
                        SessionORM.is_revoked.is_(False),
                    )
                    .values(is_revoked=True, revoked_at=datetime.now(UTC))
                )
                await session.commit()
                return int(result.rowcount or 0)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to revoke user sessions",
                    context={"user_id": user_id, "error": str(exc)},
                ) from exc

    async def cleanup_expired(self) -> int:
        """Delete sessions that are both expired and revoked.

        Returns:
            Number of rows deleted.
        """
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            try:
                result = await session.execute(
                    delete(SessionORM).where(
                        and_(
                            SessionORM.expires_at < now,
                            SessionORM.is_revoked.is_(True),
                        )
                    )
                )
                await session.commit()
                return int(result.rowcount or 0)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to cleanup expired sessions",
                    context={"error": str(exc)},
                ) from exc

    async def is_token_revoked(self, jti: str) -> bool:
        """Return whether a JWT ID is revoked (or unknown/expired).

        Args:
            jti: JWT ID claim.

        Returns:
            ``True`` if revoked or missing; ``False`` if an active session exists.
        """
        session_row = await self.get_by_jti(jti)
        if session_row is None:
            return False
        if session_row.is_revoked:
            return True
        expires = session_row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return expires < datetime.now(UTC)
