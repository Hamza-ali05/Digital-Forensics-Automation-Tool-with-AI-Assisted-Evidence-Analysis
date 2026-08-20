"""Dataset intelligence registry ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DatasetRecordORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted dataset metadata and enrichment results."""

    __tablename__ = "dataset_records"
    __table_args__ = (
        Index("ix_dataset_records_category_status", "category", "status"),
        Index("ix_dataset_records_hash_active", "hash_sha256", "is_deleted"),
        Index("ix_dataset_records_format_status", "format", "status"),
    )

    dataset_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(1024), unique=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    format: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    hash_sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    validated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    indexed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    parent_directory: Mapped[str] = mapped_column(String(1024))
    is_nested: Mapped[bool] = mapped_column(Boolean, default=False)
    nested_depth: Mapped[int] = mapped_column(default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    associated_research_objectives_json: Mapped[str] = mapped_column(Text, default="[]")
    supported_forensic_modules_json: Mapped[str] = mapped_column(Text, default="[]")
    indexing_status: Mapped[str] = mapped_column(String(30), default="pending")
    preprocessing_history_json: Mapped[str] = mapped_column(Text, default="[]")
    update_history_json: Mapped[str] = mapped_column(Text, default="[]")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    file_modified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
