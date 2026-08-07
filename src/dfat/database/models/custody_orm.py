"""Append-only chain-of-custody ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dfat.database.base import Base, UUIDPrimaryKeyMixin


class ChainOfCustodyORM(Base, UUIDPrimaryKeyMixin):
    """Insert-only custody event (no ``updated_at``; never UPDATE/DELETE)."""

    __tablename__ = "chain_of_custody"
    __table_args__ = (
        Index("ix_custody_evidence_entry", "evidence_id", "entry_number"),
    )

    evidence_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_records.id"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(30))
    performed_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    performed_by_name: Mapped[str] = mapped_column(String(255))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text)
    hash_at_action: Mapped[str] = mapped_column(String(128))
    location: Mapped[str] = mapped_column(
        String(255),
        default="DFAT Local System",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry_number: Mapped[int] = mapped_column(Integer)
