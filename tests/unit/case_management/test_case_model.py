"""Unit tests for Case and CaseInvestigator domain models."""

from __future__ import annotations

from datetime import UTC, datetime

from dfat.case_management.enums import CaseStatus
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evidence import CaseMetadata


def test_case_wraps_case_metadata(sample_case_metadata: CaseMetadata) -> None:
    """Case embeds CaseMetadata without mutating it."""
    # Arrange / Act
    case = Case(metadata=sample_case_metadata)

    # Assert
    assert case.metadata is sample_case_metadata
    assert case.case_id == sample_case_metadata.case_id
    assert case.case_name == sample_case_metadata.case_name


def test_case_computed_fields(sample_case: Case) -> None:
    """Computed evidence/investigator counts reflect list lengths."""
    # Arrange
    sample_case.evidence_ids = ["e1", "e2"]
    sample_case.investigators = [
        CaseInvestigator(
            user_id="u1",
            username="alice",
            full_name="Alice",
            role="lead",
        )
    ]

    # Act / Assert
    assert sample_case.evidence_count == 2
    assert sample_case.investigator_count == 1


def test_case_defaults(sample_case_metadata: CaseMetadata) -> None:
    """New cases default to CREATED with empty collections."""
    # Arrange / Act
    case = Case(metadata=sample_case_metadata)

    # Assert
    assert case.status is CaseStatus.CREATED
    assert case.investigators == []
    assert case.evidence_ids == []
    assert case.lead_investigator_id is None
    assert case.opened_at is None
    assert case.closed_at is None


def test_case_investigator_model() -> None:
    """CaseInvestigator stores role and assignment timestamp."""
    # Arrange
    assigned = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

    # Act
    investigator = CaseInvestigator(
        user_id="u1",
        username="bob",
        full_name="Bob",
        role="member",
        assigned_at=assigned,
    )

    # Assert
    assert investigator.role == "member"
    assert investigator.assigned_at == assigned
    assert investigator.username == "bob"
