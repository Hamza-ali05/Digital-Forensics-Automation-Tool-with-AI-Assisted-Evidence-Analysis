"""ORM model for persisted AI analysis operation records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIAnalysisRecordORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted metadata for an AI classification/summary/explain/Q&A run.

    Stores operational telemetry only — never prompt text or evidence bodies.
    """

    __tablename__ = "ai_analysis_records"
    __table_args__ = (
        Index("ix_ai_analysis_evidence_type", "evidence_id", "analysis_type"),
    )

    job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    evidence_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    analysis_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    input_artefact_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    output_token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0",
    )
    duration_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0",
    )
    hallucination_risk: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    cache_hit: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
