"""Append-only forensic audit log ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, UUIDPrimaryKeyMixin


class AuditLogRecordORM(Base, UUIDPrimaryKeyMixin):
    """Insert-only audit trail row (no ``updated_at``; never UPDATE/DELETE)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_evidence_timestamp", "evidence_id", "timestamp"),
        Index("ix_audit_user_timestamp", "user_id", "timestamp"),
    )

    entry_number: Mapped[int] = mapped_column(Integer, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    stage: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(255))
    evidence_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    hash_before: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    hash_after: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    details: Mapped[str] = mapped_column(Text, default="{}")
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
