"""Unit tests for core domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import CaseMetadata, EvidenceImage


def test_case_metadata_creation_succeeds_with_required_fields() -> None:
    """Verify CaseMetadata can be created with required fields."""
    # Arrange / Act
    case = CaseMetadata(case_name="Case A", investigator="Bob")

    # Assert
    assert case.case_name == "Case A"
    assert case.investigator == "Bob"
    assert case.case_id


def test_evidence_image_serialisation_roundtrip_preserves_fields(
    sample_evidence_image: EvidenceImage,
) -> None:
    """Verify EvidenceImage serialises and deserialises without data loss."""
    # Arrange
    payload = sample_evidence_image.model_dump(mode="json")

    # Act
    restored = EvidenceImage.model_validate(payload)

    # Assert
    assert restored.evidence_id == sample_evidence_image.evidence_id
    assert restored.evidence_type == EvidenceType.DISK_IMAGE
    assert restored.hash_algorithm == HashAlgorithm.SHA256


def test_artefact_set_total_count_matches_list_length(
    sample_artefact_set: ArtefactSet,
) -> None:
    """Verify ArtefactSet.total_count equals the artefacts list length."""
    # Arrange / Act / Assert
    assert sample_artefact_set.total_count == 5
    assert sample_artefact_set.total_count == len(sample_artefact_set.artefacts)


def test_artefact_creation_rejects_invalid_category() -> None:
    """Verify Artefact validation rejects an invalid category value."""
    # Arrange / Act / Assert
    with pytest.raises(ValidationError):
        Artefact(
            category="not_a_real_category",  # type: ignore[arg-type]
            source_evidence_id="ev-1",
            raw_data={},
        )
