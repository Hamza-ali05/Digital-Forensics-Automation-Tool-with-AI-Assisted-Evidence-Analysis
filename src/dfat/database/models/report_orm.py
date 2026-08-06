"""Forensic report ORM model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReportRecordORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted dual-output forensic report."""

    __tablename__ = "report_records"

    case_id: Mapped[str] = mapped_column(String(36), index=True)
    evidence_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evidence_records.id"),
    )
    json_report_data: Mapped[str] = mapped_column(Text)
    narrative_text: Mapped[str] = mapped_column(Text)
    llm_model_used: Mapped[str] = mapped_column(String(100))
    generation_parameters: Mapped[str] = mapped_column(Text, default="{}")
    integrity_hash: Mapped[str] = mapped_column(String(128))
    schema_version: Mapped[str] = mapped_column(String(20))
    pipeline_duration_seconds: Mapped[float] = mapped_column(Float)
    stage_timings: Mapped[str] = mapped_column(Text, default="{}")
    generated_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
