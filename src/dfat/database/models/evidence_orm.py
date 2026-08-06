"""Evidence metadata ORM model (no raw evidence blobs)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceRecordORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted evidence metadata and integrity hash reference."""

    __tablename__ = "evidence_records"

    case_id: Mapped[str] = mapped_column(String(36), index=True)
    case_name: Mapped[str] = mapped_column(String(255))
    investigator: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(1024))
    evidence_type: Mapped[str] = mapped_column(String(50))
    original_hash: Mapped[str] = mapped_column(String(128))
    hash_algorithm: Mapped[str] = mapped_column(String(20))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    acquired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    volatility_profile: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    registered_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
