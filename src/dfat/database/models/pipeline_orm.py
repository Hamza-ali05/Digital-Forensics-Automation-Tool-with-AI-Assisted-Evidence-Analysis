"""Pipeline job ORM model for persisted pipeline execution records."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PipelineJobORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted pipeline job record (mirrors domain ``PipelineJob``).

    ``id`` stores the domain ``job_id``. Stage execution details are serialised
    as JSON text in ``stage_executions``.
    """

    __tablename__ = "pipeline_jobs"

    evidence_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        index=True,
        nullable=False,
        default="queued",
        server_default="queued",
    )
    mode: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="full",
        server_default="full",
    )
    use_fallback_analyzer: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    total_duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    current_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    stage_executions: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artefact_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    report_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
