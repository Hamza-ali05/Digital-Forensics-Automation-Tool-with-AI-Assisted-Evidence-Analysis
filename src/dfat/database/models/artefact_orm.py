"""Artefact record ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ArtefactRecordORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted extracted or ranked artefact row."""

    __tablename__ = "artefact_records"
    __table_args__ = (
        Index("ix_artefact_evidence_category", "evidence_id", "category"),
    )

    evidence_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evidence_records.id"),
        index=True,
    )
    category: Mapped[str] = mapped_column(String(50), index=True)
    source_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    raw_data: Mapped[str] = mapped_column(Text)
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    suspicion_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    relevance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    classification_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
