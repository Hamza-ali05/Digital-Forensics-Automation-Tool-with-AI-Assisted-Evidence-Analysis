"""Unit tests for core enumerations."""

from __future__ import annotations

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType, PipelineStage, SuspicionLevel


def test_evidence_type_membership_includes_disk_and_memory() -> None:
    """Verify EvidenceType contains disk_image and memory_dump members."""
    # Arrange / Act / Assert
    assert EvidenceType.DISK_IMAGE.value == "disk_image"
    assert EvidenceType.MEMORY_DUMP.value == "memory_dump"
    assert EvidenceType("disk_image") is EvidenceType.DISK_IMAGE


def test_pipeline_stage_values_cover_five_stages() -> None:
    """Verify PipelineStage enumerates all five pipeline stages."""
    # Arrange
    expected = {
        "acquisition",
        "parsing",
        "ai_triage",
        "reporting",
        "evaluation",
    }

    # Act
    actual = {stage.value for stage in PipelineStage}

    # Assert
    assert actual == expected


def test_suspicion_level_rejects_unknown_value() -> None:
    """Verify SuspicionLevel raises ValueError for unknown members."""
    # Arrange / Act / Assert
    with pytest.raises(ValueError):
        SuspicionLevel("ultra_critical")


def test_artefact_category_membership_contains_registry_key() -> None:
    """Verify ArtefactCategory includes registry_key."""
    # Arrange / Act / Assert
    assert ArtefactCategory.REGISTRY_KEY in ArtefactCategory
    assert ArtefactCategory.REGISTRY_KEY.value == "registry_key"
