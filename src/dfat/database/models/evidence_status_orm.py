"""Evidence status history and metadata ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceStatusHistoryORM(Base, UUIDPrimaryKeyMixin):
    """Insert-only evidence status transition (no ``updated_at``)."""

    __tablename__ = "evidence_status_history"

    evidence_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_records.id"),
        index=True,
    )
    previous_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30))
    changed_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text)


class EvidenceMetadataORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Extracted metadata and multi-algorithm hashes for evidence."""

    __tablename__ = "evidence_metadata"

    evidence_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_records.id"),
        unique=True,
        index=True,
    )
    mime_type: Mapped[str] = mapped_column(String(100))
    mime_detected_from: Mapped[str] = mapped_column(String(50))
    file_extension: Mapped[str] = mapped_column(String(20))
    file_size_bytes: Mapped[int] = mapped_column(default=0)
    file_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    file_modified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    file_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    hash_md5: Mapped[str] = mapped_column(String(32))
    hash_sha1: Mapped[str] = mapped_column(String(40))
    hash_sha256: Mapped[str] = mapped_column(String(64))
    hash_computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_valid_format: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_notes: Mapped[str] = mapped_column(Text, default="[]")
