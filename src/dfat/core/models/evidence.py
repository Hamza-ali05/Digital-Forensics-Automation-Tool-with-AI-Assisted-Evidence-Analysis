"""Evidence and case metadata domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import EvidenceType, HashAlgorithm


class CaseMetadata(BaseModel):
    """Case-level metadata associated with forensic evidence.

    Attributes:
        case_id: Unique case identifier.
        case_name: Human-readable case name.
        investigator: Investigator or analyst name.
        created_at: UTC timestamp when the case record was created.
        description: Optional free-text case description.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    case_id: str = Field(default_factory=lambda: str(uuid4()))
    case_name: str
    investigator: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    description: Optional[str] = None


class EvidenceImage(BaseModel):
    """Forensic disk image or generic evidence container metadata.

    Attributes:
        evidence_id: Unique evidence identifier.
        file_path: Path to the acquired evidence file (read-only usage).
        evidence_type: Disk image or memory dump classification.
        original_hash: Integrity hash of the original evidence.
        hash_algorithm: Algorithm used to compute ``original_hash``.
        file_size_bytes: Size of the evidence file in bytes.
        acquired_at: Optional acquisition timestamp.
        case: Associated case metadata.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    file_path: Path
    evidence_type: EvidenceType
    original_hash: str
    hash_algorithm: HashAlgorithm
    file_size_bytes: int
    acquired_at: Optional[datetime] = None
    case: CaseMetadata


class MemoryDump(EvidenceImage):
    """Memory dump evidence with optional Volatility profile metadata.

    Attributes:
        volatility_profile: Optional Volatility3 profile name.
        capture_timestamp: Optional memory capture timestamp.
    """

    volatility_profile: Optional[str] = None
    capture_timestamp: Optional[datetime] = None
