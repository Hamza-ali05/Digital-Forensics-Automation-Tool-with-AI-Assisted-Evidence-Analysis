"""Unit tests for ArtefactNormalizer merge/dedup behaviour."""

from __future__ import annotations

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.normalizer import ArtefactNormalizer


def _artefact(artefact_id: str, category: ArtefactCategory, evidence_id: str) -> Artefact:
    """Build a minimal artefact for normalisation tests."""
    return Artefact(
        artefact_id=artefact_id,
        category=category,
        source_evidence_id=evidence_id,
        raw_data={"id": artefact_id},
    )


def test_normalize_merges_parser_results() -> None:
    """Verify artefacts from multiple parsers are merged into one set."""
    # Arrange
    evidence_id = "ev-1"
    set_a = ArtefactSet(
        evidence_id=evidence_id,
        artefacts=[
            _artefact("a1", ArtefactCategory.FILESYSTEM_METADATA, evidence_id),
        ],
        categories_present=[ArtefactCategory.FILESYSTEM_METADATA],
    )
    set_b = ArtefactSet(
        evidence_id=evidence_id,
        artefacts=[
            _artefact("b1", ArtefactCategory.REGISTRY_KEY, evidence_id),
        ],
        categories_present=[ArtefactCategory.REGISTRY_KEY],
    )
    normalizer = ArtefactNormalizer()

    # Act
    merged = normalizer.normalize([set_a, set_b], evidence_id)

    # Assert
    assert merged.evidence_id == evidence_id
    assert merged.total_count == 2
    assert ArtefactCategory.FILESYSTEM_METADATA in merged.categories_present
    assert ArtefactCategory.REGISTRY_KEY in merged.categories_present


def test_normalize_deduplicates_by_artefact_id() -> None:
    """Verify duplicate artefact IDs are kept only once."""
    # Arrange
    evidence_id = "ev-1"
    shared = _artefact("dup-1", ArtefactCategory.BROWSER_HISTORY, evidence_id)
    set_a = ArtefactSet(
        evidence_id=evidence_id,
        artefacts=[shared],
        categories_present=[ArtefactCategory.BROWSER_HISTORY],
    )
    set_b = ArtefactSet(
        evidence_id=evidence_id,
        artefacts=[
            shared,
            _artefact("unique-2", ArtefactCategory.EVENT_LOG, evidence_id),
        ],
        categories_present=[
            ArtefactCategory.BROWSER_HISTORY,
            ArtefactCategory.EVENT_LOG,
        ],
    )
    normalizer = ArtefactNormalizer()

    # Act
    merged = normalizer.normalize([set_a, set_b], evidence_id)

    # Assert
    assert merged.total_count == 2
    assert [a.artefact_id for a in merged.artefacts] == ["dup-1", "unique-2"]


def test_normalize_empty_input_returns_empty_set() -> None:
    """Verify empty parser outputs produce an empty ArtefactSet."""
    # Arrange
    normalizer = ArtefactNormalizer()

    # Act
    merged = normalizer.normalize([], "ev-empty")

    # Assert
    assert merged.evidence_id == "ev-empty"
    assert merged.total_count == 0
    assert merged.categories_present == []
