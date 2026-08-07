"""Pydantic request/response schemas for case management API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.case_management.enums import CaseStatus


class CreateCaseRequest(BaseModel):
    """Request body for creating an investigation case."""

    model_config = ConfigDict(str_strip_whitespace=True)

    case_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class AssignInvestigatorRequest(BaseModel):
    """Request body for assigning an investigator to a case."""

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    role: Literal["lead", "member"] = "member"


class CaseTransitionRequest(BaseModel):
    """Request body for case transitions that require a reason."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(..., min_length=1)


class AddEvidenceToCaseRequest(BaseModel):
    """Request body for linking evidence to a case."""

    model_config = ConfigDict(str_strip_whitespace=True)

    evidence_id: str = Field(..., min_length=1)


class InvestigatorResponse(BaseModel):
    """Investigator assignment in API responses."""

    user_id: str
    username: str
    full_name: str
    role: Literal["lead", "member"]
    assigned_at: datetime


class CaseResponse(BaseModel):
    """Case detail response."""

    case_id: str
    case_name: str
    description: Optional[str] = None
    status: CaseStatus
    lead_investigator_id: Optional[str] = None
    investigators: list[InvestigatorResponse] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    investigator_count: int = 0
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    closure_reason: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


class CaseSummaryResponse(BaseModel):
    """Comprehensive case summary response."""

    case_id: str
    case_name: str
    description: Optional[str] = None
    status: str
    lead_investigator_id: Optional[str] = None
    investigators: list[dict[str, Any]] = Field(default_factory=list)
    investigator_count: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    evidence_summaries: list[dict[str, Any]] = Field(default_factory=list)
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    archived_at: Optional[str] = None
    closure_reason: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: str


class CaseListResponse(BaseModel):
    """Paginated-style case list wrapper."""

    cases: list[CaseResponse]
    total: int
