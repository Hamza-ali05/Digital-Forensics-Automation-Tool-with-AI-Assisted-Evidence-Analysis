"""Unit tests for case-management enumerations and transition maps."""

from __future__ import annotations

from dfat.case_management.enums import (
    CASE_STATUS_TRANSITIONS,
    EVIDENCE_STATUS_TRANSITIONS,
    CaseStatus,
    CustodyAction,
    EvidenceStatus,
)


def test_case_status_values() -> None:
    """CaseStatus exposes the six lifecycle values."""
    # Arrange / Act
    values = {status.value for status in CaseStatus}

    # Assert
    assert values == {
        "created",
        "open",
        "active",
        "under_review",
        "closed",
        "archived",
    }


def test_evidence_and_custody_status_values() -> None:
    """EvidenceStatus and CustodyAction expose expected members."""
    # Arrange / Act / Assert
    assert EvidenceStatus.REGISTERED.value == "registered"
    assert EvidenceStatus.QUARANTINED.value == "quarantined"
    assert CustodyAction.ACQUIRED.value == "acquired"
    assert CustodyAction.SEALED.value == "sealed"


def test_case_status_transitions_happy_path() -> None:
    """Canonical happy-path transitions are declared."""
    # Arrange / Act / Assert
    assert CaseStatus.OPEN in CASE_STATUS_TRANSITIONS[CaseStatus.CREATED]
    assert CaseStatus.ACTIVE in CASE_STATUS_TRANSITIONS[CaseStatus.OPEN]
    assert CaseStatus.UNDER_REVIEW in CASE_STATUS_TRANSITIONS[CaseStatus.ACTIVE]
    assert CaseStatus.CLOSED in CASE_STATUS_TRANSITIONS[CaseStatus.UNDER_REVIEW]
    assert CaseStatus.ARCHIVED in CASE_STATUS_TRANSITIONS[CaseStatus.CLOSED]


def test_case_terminal_states() -> None:
    """ARCHIVED is terminal; CLOSED only allows ARCHIVED."""
    # Arrange / Act / Assert
    assert CASE_STATUS_TRANSITIONS[CaseStatus.ARCHIVED] == []
    assert CASE_STATUS_TRANSITIONS[CaseStatus.CLOSED] == [CaseStatus.ARCHIVED]


def test_evidence_status_transitions_include_quarantine_escape() -> None:
    """Quarantined evidence may return to REGISTERED for revalidation."""
    # Arrange / Act / Assert
    assert EvidenceStatus.QUARANTINED in EVIDENCE_STATUS_TRANSITIONS[
        EvidenceStatus.VALIDATING
    ]
    assert EvidenceStatus.REGISTERED in EVIDENCE_STATUS_TRANSITIONS[
        EvidenceStatus.QUARANTINED
    ]
    assert EVIDENCE_STATUS_TRANSITIONS[EvidenceStatus.ARCHIVED] == []
