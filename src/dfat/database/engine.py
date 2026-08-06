"""Async SQLAlchemy engine and session factory for DFAT."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from dfat.database.base import Base


class DatabaseEngine:
    """Manage the async SQLAlchemy engine and session lifecycle.

    Stores metadata, audit trails, user accounts, and analysis results only.
    Raw forensic evidence files remain on the local filesystem.
    """

    def __init__(
        self,
        database_url: str,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
    ) -> None:
        """Initialise the async engine and session factory.

        Args:
            database_url: SQLAlchemy async database URL.
            echo: Whether to log SQL statements.
            pool_size: Connection pool size (ignored for SQLite).
            max_overflow: Max overflow connections (ignored for SQLite).
        """
        engine_kwargs: dict[str, Any] = {"echo": echo}
        if database_url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in database_url:
                from sqlalchemy.pool import StaticPool

                engine_kwargs["poolclass"] = StaticPool
        else:
            engine_kwargs["pool_size"] = pool_size
            engine_kwargs["max_overflow"] = max_overflow

        self._engine: AsyncEngine = create_async_engine(database_url, **engine_kwargs)
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Return the underlying async engine."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the async session factory."""
        return self._session_factory

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield an async session with commit/rollback/close handling.

        Yields:
            An ``AsyncSession`` bound to this engine.

        Raises:
            Exception: Re-raises after rolling back on failure.
        """
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def create_tables(self) -> None:
        """Create all tables registered on ``Base.metadata``."""
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        """Drop all tables registered on ``Base.metadata`` (testing only)."""
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)

    async def dispose(self) -> None:
        """Dispose the engine connection pool."""
        await self._engine.dispose()

    async def check_connection(self) -> bool:
        """Verify database connectivity with ``SELECT 1``.

        Returns:
            ``True`` when the query succeeds; ``False`` on any failure.
        """
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001
            return False


def engine_factory(
    database_url: str,
    *,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> DatabaseEngine:
    """Create a ``DatabaseEngine`` instance.

    Args:
        database_url: SQLAlchemy async database URL.
        echo: Whether to log SQL statements.
        pool_size: Connection pool size (non-SQLite).
        max_overflow: Max overflow connections (non-SQLite).

    Returns:
        Configured ``DatabaseEngine``.
    """
    return DatabaseEngine(
        database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )


async def get_async_session(
    database_engine: DatabaseEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a session from the given database engine.

    Args:
        database_engine: Engine providing the session factory.

    Yields:
        An ``AsyncSession`` with commit/rollback/close semantics.
    """
    async for session in database_engine.get_session():
        yield session
