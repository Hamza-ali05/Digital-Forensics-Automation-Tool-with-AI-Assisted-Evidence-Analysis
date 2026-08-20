"""ORM models for ML experiment and trained-model metadata."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MLExperimentORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted ML experiment run metadata."""

    __tablename__ = "ml_experiments"
    __table_args__ = (
        Index("ix_ml_experiments_model_status", "model_name", "status"),
    )

    experiment_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running", index=True)
    hyperparameters_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[str] = mapped_column(String(40), nullable=False)
    completed_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    artifact_paths_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class MLModelRecordORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted trained-model registry metadata."""

    __tablename__ = "ml_model_records"
    __table_args__ = (
        Index("ix_ml_model_records_name_version", "model_name", "version"),
    )

    model_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    model_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    training_dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    hyperparameters_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    feature_names_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    trained_at: Mapped[str] = mapped_column(String(40), nullable=False)
