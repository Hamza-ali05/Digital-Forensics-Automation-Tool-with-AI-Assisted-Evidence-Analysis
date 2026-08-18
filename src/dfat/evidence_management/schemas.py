"""Pydantic request/response schemas for evidence management API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dfat.api.path_safety import assert_no_path_traversal

from dfat.api.schemas.base import APIModel
from dfat.case_management.enums import EvidenceStatus
from dfat.core.enums import EvidenceType


class RegisterEvidenceRequest(BaseModel):
    """Request body for register-and-validate evidence workflow."""

    model_config = ConfigDict(str_strip_whitespace=True)

    file_path: str = Field(..., min_length=1)
    case_id: str = Field(..., min_length=1)
    evidence_type: EvidenceType
    description: Optional[str] = None

    @field_validator("file_path")
    @classmethod
    def _reject_traversal(cls, value: str) -> str:
        return assert_no_path_traversal(value)


class QuarantineEvidenceRequest(BaseModel):
    """Request body for quarantining evidence."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(..., min_length=1)


class EvidenceDetailResponse(APIModel):
    """Comprehensive evidence detail response."""

    evidence_id: str
    file_path: str
    evidence_type: str
    original_hash: str
    hash_algorithm: str
    file_size_bytes: int
    acquired_at: Optional[str] = None
    case_id: str
    case_name: str
    case_status: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    status_history: list[dict[str, Any]] = Field(default_factory=list)
    custody_chain: list[dict[str, Any]] = Field(default_factory=list)
    custody_actions_count: int = 0


class EvidenceInventoryItemResponse(APIModel):
    """Single inventory row."""

    evidence_id: str
    case_id: str
    case_name: str
    file_name: str
    evidence_type: EvidenceType
    status: EvidenceStatus
    hash_set: Optional[dict[str, Any]] = None
    mime_type: Optional[str] = None
    file_size_bytes: int
    registered_at: datetime
    last_verified_at: Optional[datetime] = None
    custody_actions_count: int = 0


class EvidenceInventoryResponse(APIModel):
    """Evidence inventory list response."""

    items: list[EvidenceInventoryItemResponse]
    total: int


class EvidenceValidationResponse(APIModel):
    """Register/validate workflow or re-validation response."""

    evidence_id: Optional[str] = None
    validation_passed: bool
    metadata: Optional[dict[str, Any]] = None
    custody_record: Optional[dict[str, Any]] = None
    validation_failures: list[str] = Field(default_factory=list)
    case_id: Optional[str] = None


class CustodyChainEntryResponse(APIModel):
    """Single custody chain entry."""

    entry_number: Optional[int] = None
    record_id: str
    action: str
    performed_by_user_id: str
    performed_by_name: str
    timestamp: datetime
    reason: str
    hash_at_action: str
    location: str = "DFAT Local System"
    notes: Optional[str] = None


class CustodyChainResponse(APIModel):
    """Ordered custody chain for an evidence item."""

    evidence_id: str
    entries: list[CustodyChainEntryResponse]
    total_entries: int


class EvidenceStatusHistoryEntry(APIModel):
    """Single evidence status history entry."""

    previous_status: Optional[str] = None
    new_status: str
    changed_by_user_id: str
    changed_at: datetime
    reason: str


class EvidenceStatusResponse(APIModel):
    """Current evidence status and history."""

    evidence_id: str
    current_status: Optional[str] = None
    history: list[EvidenceStatusHistoryEntry] = Field(default_factory=list)


class IntegrityVerificationResponse(APIModel):
    """Integrity verification result."""

    evidence_id: str
    integrity_verified: bool
    hash_set: dict[str, Any] = Field(default_factory=dict)
    timestamp: str
    discrepancies: dict[str, Any] = Field(default_factory=dict)
    custody_record: Optional[dict[str, Any]] = None


class EvidenceStatisticsResponse(APIModel):
    """Aggregated evidence statistics."""

    total: int
    by_type: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    total_size: int
    avg_custody_chain_length: float
    case_id: Optional[str] = None
