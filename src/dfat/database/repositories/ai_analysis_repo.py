"""AI analysis record repository."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.database.exceptions import DatabaseError
from dfat.database.models.ai_orm import AIAnalysisRecordORM


class SQLAlchemyAIAnalysisRepository:
    """Persist and load ``AIAnalysisRecordORM`` rows."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def save(self, record: AIAnalysisRecordORM) -> AIAnalysisRecordORM:
        """Insert an AI analysis record and return it with generated ID."""
        async with self._session_factory() as session:
            try:
                session.add(record)
                await session.commit()
                await session.refresh(record)
                return record
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to save AI analysis record",
                    context={
                        "evidence_id": record.evidence_id,
                        "analysis_type": record.analysis_type,
                        "error": str(exc),
                    },
                ) from exc

    async def get(self, record_id: str) -> Optional[AIAnalysisRecordORM]:
        """Load an AI analysis record by primary key."""
        async with self._session_factory() as session:
            try:
                return await session.get(AIAnalysisRecordORM, record_id)
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load AI analysis record",
                    context={"record_id": record_id, "error": str(exc)},
                ) from exc
