"""Benchmark and usability evaluation ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BenchmarkRecordORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted benchmark evaluation metrics."""

    __tablename__ = "benchmark_records"

    dataset_name: Mapped[str] = mapped_column(String(255))
    evidence_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    precision_val: Mapped[float] = mapped_column(Float)
    recall_val: Mapped[float] = mapped_column(Float)
    f1_score: Mapped[float] = mapped_column(Float)
    time_to_triage_seconds: Mapped[float] = mapped_column(Float)
    artefacts_expected: Mapped[int] = mapped_column(Integer)
    artefacts_recovered: Mapped[int] = mapped_column(Integer)
    false_positives: Mapped[int] = mapped_column(Integer)
    false_negatives: Mapped[int] = mapped_column(Integer)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UsabilityRecordORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted anonymised usability questionnaire response."""

    __tablename__ = "usability_records"

    participant_id: Mapped[str] = mapped_column(String(36))
    usefulness_rating: Mapped[int] = mapped_column(Integer)
    accuracy_rating: Mapped[int] = mapped_column(Integer)
    clarity_rating: Mapped[int] = mapped_column(Integer)
    free_text_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
