"""Evidence management domain models (hashes, metadata, custody, inventory)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dfat.case_management.enums import CustodyAction, EvidenceStatus
from dfat.core.enums import EvidenceType


class HashSet(BaseModel):
    """Multi-algorithm integrity fingerprint for an evidence file.

    Attributes:
        md5: MD5 digest (hex).
        sha1: SHA-1 digest (hex).
        sha256: SHA-256 digest (hex) — primary integrity hash.
        computed_at: UTC timestamp when hashes were computed.
        file_size_bytes: Size of the hashed file in bytes.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    md5: str
    sha1: str
    sha256: str
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    file_size_bytes: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def primary_hash(self) -> str:
        """Return the SHA-256 digest as the primary integrity hash."""
        return self.sha256


class EvidenceMetadataRecord(BaseModel):
    """Extracted metadata and validation notes for registered evidence.

    Attributes:
        evidence_id: Related evidence identifier.
        mime_type: Detected or declared MIME type.
        mime_detected_from: How MIME type was determined.
        file_extension: Lowercase file extension including the dot.
        file_size_bytes: File size in bytes.
        file_created_at: Optional filesystem created timestamp.
        file_modified_at: Optional filesystem modified timestamp.
        file_accessed_at: Optional filesystem accessed timestamp.
        hash_set: Multi-algorithm hash fingerprint.
        is_valid_format: Whether format validation succeeded.
        validation_notes: Human-readable validation notes.
        extracted_at: UTC timestamp of metadata extraction.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    evidence_id: str
    mime_type: str
    mime_detected_from: str
    file_extension: str
    file_size_bytes: int
    file_created_at: Optional[datetime] = None
    file_modified_at: Optional[datetime] = None
    file_accessed_at: Optional[datetime] = None
    hash_set: HashSet
    is_valid_format: bool
    validation_notes: list[str] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChainOfCustodyRecord(BaseModel):
    """Append-only chain-of-custody event for an evidence item.

    Attributes:
        record_id: Unique custody record identifier.
        evidence_id: Related evidence identifier.
        action: Custody action performed.
        performed_by_user_id: Acting user ID.
        performed_by_name: Acting user display name.
        timestamp: UTC event timestamp.
        reason: Reason for the custody action.
        hash_at_action: Integrity hash recorded at the time of the action.
        location: Physical/logical location (local system by default).
        notes: Optional free-text notes.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    record_id: str = Field(default_factory=lambda: str(uuid4()))
    evidence_id: str
    action: CustodyAction
    performed_by_user_id: str
    performed_by_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str
    hash_at_action: str
    location: str = "DFAT Local System"
    notes: Optional[str] = None
    entry_number: Optional[int] = None


class EvidenceStatusChange(BaseModel):
    """Record of an evidence status transition.

    Attributes:
        evidence_id: Related evidence identifier.
        previous_status: Status before the change (None on first registration).
        new_status: Status after the change.
        changed_by_user_id: Acting user ID.
        changed_at: UTC timestamp of the change.
        reason: Reason for the status change.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    evidence_id: str
    previous_status: Optional[EvidenceStatus] = None
    new_status: EvidenceStatus
    changed_by_user_id: str
    changed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str


class EvidenceInventoryItem(BaseModel):
    """Summary row for evidence inventory listings.

    Attributes:
        evidence_id: Evidence identifier.
        case_id: Owning case identifier.
        case_name: Owning case display name.
        file_name: Evidence file name (not full path for display).
        evidence_type: Disk image or memory dump.
        status: Current evidence status.
        hash_set: Optional multi-algorithm hash fingerprint.
        mime_type: Optional MIME type.
        file_size_bytes: File size in bytes.
        registered_at: UTC registration timestamp.
        last_verified_at: Optional last integrity verification timestamp.
        custody_actions_count: Number of custody records for this evidence.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    evidence_id: str
    case_id: str
    case_name: str
    file_name: str
    evidence_type: EvidenceType
    status: EvidenceStatus
    hash_set: Optional[HashSet] = None
    mime_type: Optional[str] = None
    file_size_bytes: int
    registered_at: datetime
    last_verified_at: Optional[datetime] = None
    custody_actions_count: int = 0
