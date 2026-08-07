"""Unit tests for ArtefactCategoriser."""

from __future__ import annotations

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.processing.categoriser import ArtefactCategoriser


def test_categorise_marks_valid_schema() -> None:
    """Verify valid process artefacts are schema_valid."""
    # Arrange
    artefact = Artefact(
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev-1",
        raw_data={"pid": 1, "name": "cmd.exe"},
    )
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[artefact],
        categories_present=[ArtefactCategory.RUNNING_PROCESS],
    )

    # Act
    result = ArtefactCategoriser().categorise(artefact_set)

    # Assert
    assert result.artefacts[0].metadata.get("schema_valid") is True


def test_categorise_marks_invalid_schema() -> None:
    """Verify missing required keys set schema_valid False."""
    # Arrange
    artefact = Artefact(
        category=ArtefactCategory.BROWSER_HISTORY,
        source_evidence_id="ev-1",
        raw_data={"url": "https://example.com"},  # missing title/visit_count/browser_type
    )
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[artefact],
        categories_present=[ArtefactCategory.BROWSER_HISTORY],
    )

    # Act
    result = ArtefactCategoriser().categorise(artefact_set)

    # Assert
    assert result.artefacts[0].metadata.get("schema_valid") is False


def test_categorise_adds_registry_autorun_subcategory() -> None:
    """Verify autorun registry keys receive a sub_category enrichment."""
    # Arrange
    artefact = Artefact(
        category=ArtefactCategory.REGISTRY_KEY,
        source_evidence_id="ev-1",
        raw_data={
            "hive_name": "SOFTWARE",
            "key_path": r"Microsoft\Windows\CurrentVersion\Run\Evil",
            "value_name": "Evil",
            "value_data": "C:\\Temp\\evil.exe",
            "value_type": "RegSZ",
        },
    )
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[artefact],
        categories_present=[ArtefactCategory.REGISTRY_KEY],
    )

    # Act
    result = ArtefactCategoriser().categorise(artefact_set)

    # Assert
    assert result.artefacts[0].metadata.get("schema_valid") is True
    assert result.artefacts[0].metadata.get("sub_category") is not None
