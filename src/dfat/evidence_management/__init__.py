"""DFAT Evidence Management — validation, integrity, chain-of-custody, metadata."""

from dfat.evidence_management.exceptions import (
    CustodyChainError,
    CustodyRecordNotFoundError,
    EvidenceManagementError,
    EvidenceQuarantinedError,
    EvidenceValidationError,
    InvalidEvidenceTransitionError,
    MIMETypeMismatchError,
)
from dfat.evidence_management.mime_identifier import (
    EXTENSION_MIME_MAP,
    FORENSIC_MIME_MAP,
    MIMEIdentifier,
)
from dfat.evidence_management.models import (
    ChainOfCustodyRecord,
    EvidenceInventoryItem,
    EvidenceMetadataRecord,
    EvidenceStatusChange,
    HashSet,
)

# Services (MultiHashService, EvidenceValidationService, ChainOfCustodyService)
# are imported from their modules to avoid circular imports with database.mappers.

__all__ = [
    "EXTENSION_MIME_MAP",
    "FORENSIC_MIME_MAP",
    "ChainOfCustodyRecord",
    "CustodyChainError",
    "CustodyRecordNotFoundError",
    "EvidenceInventoryItem",
    "EvidenceManagementError",
    "EvidenceMetadataRecord",
    "EvidenceQuarantinedError",
    "EvidenceStatusChange",
    "EvidenceValidationError",
    "HashSet",
    "InvalidEvidenceTransitionError",
    "MIMEIdentifier",
    "MIMETypeMismatchError",
]
