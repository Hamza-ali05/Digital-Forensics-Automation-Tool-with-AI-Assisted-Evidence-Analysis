"""Full investigation case lifecycle domain model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dfat.case_management.enums import CaseStatus
from dfat.core.models.evidence import CaseMetadata


class CaseInvestigator(BaseModel):
    """Investigator assignment on a case.

    Attributes:
        user_id: Assigned user identifier.
        username: Account username.
        full_name: Display name.
        role: ``lead`` or ``member``.
        assigned_at: UTC assignment timestamp.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    user_id: str
    username: str
    full_name: str
    role: Literal["lead", "member"]
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Case(BaseModel):
    """Full case lifecycle model.

    Wraps :class:`~dfat.core.models.evidence.CaseMetadata` for backward
    compatibility with the Prompt 1 domain layer. Pipeline and acquisition
    code continue to use ``CaseMetadata``; case management uses ``Case``.

    Attributes:
        metadata: Embedded Prompt 1 case metadata.
        status: Lifecycle status.
        investigators: Assigned investigators.
        lead_investigator_id: User ID of the lead investigator.
        evidence_ids: Registered evidence identifiers for this case.
        opened_at: When the case was opened.
        closed_at: When the case was closed.
        archived_at: When the case was archived.
        closure_reason: Optional reason recorded on close.
        notes: Free-text case notes.
        tags: Searchable tags.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    metadata: CaseMetadata
    status: CaseStatus = CaseStatus.CREATED
    investigators: list[CaseInvestigator] = Field(default_factory=list)
    lead_investigator_id: Optional[str] = None
    evidence_ids: list[str] = Field(default_factory=list)
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    closure_reason: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def case_id(self) -> str:
        """Delegate to embedded metadata case identifier."""
        return self.metadata.case_id

    @computed_field  # type: ignore[prop-decorator]
    @property
    def case_name(self) -> str:
        """Delegate to embedded metadata case name."""
        return self.metadata.case_name

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_count(self) -> int:
        """Return the number of linked evidence identifiers."""
        return len(self.evidence_ids)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def investigator_count(self) -> int:
        """Return the number of assigned investigators."""
        return len(self.investigators)
