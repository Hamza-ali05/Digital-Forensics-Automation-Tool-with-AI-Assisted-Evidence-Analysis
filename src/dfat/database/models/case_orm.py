"""Case and investigator-assignment ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dfat.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CaseORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Investigation case with lifecycle status and investigator links."""

    __tablename__ = "cases"

    case_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="created", index=True)
    lead_investigator_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="[]")
    tags: Mapped[str] = mapped_column(Text, default="[]")

    investigators: Mapped[list[CaseInvestigatorORM]] = relationship(
        "CaseInvestigatorORM",
        back_populates="case",
        cascade="all, delete-orphan",
    )


class CaseInvestigatorORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Investigator assignment on a case (lead or member)."""

    __tablename__ = "case_investigators"
    __table_args__ = (
        UniqueConstraint("case_id", "user_id", name="uq_case_investigators_case_user"),
    )

    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    case: Mapped[CaseORM] = relationship("CaseORM", back_populates="investigators")
