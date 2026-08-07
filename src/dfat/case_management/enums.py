"""Case lifecycle, evidence status, and custody-action enumerations."""

from __future__ import annotations

from enum import Enum


class CaseStatus(str, Enum):
    """Investigation case lifecycle status."""

    CREATED = "created"
    OPEN = "open"
    ACTIVE = "active"
    UNDER_REVIEW = "under_review"
    CLOSED = "closed"
    ARCHIVED = "archived"


class EvidenceStatus(str, Enum):
    """Evidence item processing status within a case."""

    REGISTERED = "registered"
    VALIDATING = "validating"
    VALIDATED = "validated"
    PROCESSING = "processing"
    PROCESSED = "processed"
    QUARANTINED = "quarantined"
    ARCHIVED = "archived"


class CustodyAction(str, Enum):
    """Chain-of-custody action recorded against evidence."""

    ACQUIRED = "acquired"
    TRANSFERRED = "transferred"
    ACCESSED = "accessed"
    ANALYSED = "analysed"
    RELEASED = "released"
    SEALED = "sealed"


CASE_STATUS_TRANSITIONS: dict[CaseStatus, list[CaseStatus]] = {
    CaseStatus.CREATED: [CaseStatus.OPEN],
    CaseStatus.OPEN: [CaseStatus.ACTIVE, CaseStatus.CLOSED],
    CaseStatus.ACTIVE: [CaseStatus.UNDER_REVIEW, CaseStatus.CLOSED],
    CaseStatus.UNDER_REVIEW: [CaseStatus.ACTIVE, CaseStatus.CLOSED],
    CaseStatus.CLOSED: [CaseStatus.ARCHIVED],
    CaseStatus.ARCHIVED: [],
}

EVIDENCE_STATUS_TRANSITIONS: dict[EvidenceStatus, list[EvidenceStatus]] = {
    EvidenceStatus.REGISTERED: [EvidenceStatus.VALIDATING],
    EvidenceStatus.VALIDATING: [
        EvidenceStatus.VALIDATED,
        EvidenceStatus.QUARANTINED,
    ],
    EvidenceStatus.VALIDATED: [EvidenceStatus.PROCESSING],
    EvidenceStatus.PROCESSING: [
        EvidenceStatus.PROCESSED,
        EvidenceStatus.QUARANTINED,
    ],
    EvidenceStatus.PROCESSED: [EvidenceStatus.ARCHIVED],
    EvidenceStatus.QUARANTINED: [EvidenceStatus.REGISTERED],
    EvidenceStatus.ARCHIVED: [],
}
