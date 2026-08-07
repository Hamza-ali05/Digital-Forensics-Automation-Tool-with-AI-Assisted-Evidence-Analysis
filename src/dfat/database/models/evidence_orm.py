"""Evidence metadata ORM model (no raw evidence blobs)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceRecordORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted evidence metadata and integrity hash reference.

    ``case_id`` stores the Prompt 1 ``CaseMetadata.case_id`` and correlates with
    ``cases.id`` when a case-management row exists. Prompt 3 additive columns
    ``status``, ``hash_md5``, and ``hash_sha1`` are nullable for backward
    compatibility with existing rows.
    """

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
    # Prompt 3 additive columns (nullable — existing rows remain valid).
    status: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        default="registered",
        server_default="registered",
    )
    hash_md5: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    hash_sha1: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
