"""Unit tests for structured JSON report export."""

from __future__ import annotations

from pathlib import Path

from dfat.core.enums import HashAlgorithm
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.reporting.json_layer import StructuredJSONExporter


def _exporter() -> StructuredJSONExporter:
    """Build exporter using the packaged report schema."""
    schema = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "dfat"
        / "reporting"
        / "templates"
        / "report_schema.json"
    )
    return StructuredJSONExporter(schema_path=schema, hash_algorithm=HashAlgorithm.SHA256)


def test_export_produces_integrity_hash(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify export produces a non-empty integrity hash."""
    # Arrange
    exporter = _exporter()

    # Act
    report = exporter.export(
        sample_artefact_set,
        sample_ranked_artefacts,
        sample_case_metadata,
        {"acquisition_s": 1.0, "parsing_s": 1.0, "triage_s": 1.0, "reporting_s": 0.5},
    )

    # Assert
    assert report.integrity_hash
    assert len(report.integrity_hash) == 64


def test_export_hash_is_deterministic_for_same_artefacts(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify identical artefact inputs yield identical integrity hashes."""
    # Arrange
    exporter = _exporter()
    timings = {"acquisition_s": 1.0, "parsing_s": 1.0, "triage_s": 1.0, "reporting_s": 0.5}

    # Act
    first = exporter.export(
        sample_artefact_set,
        sample_ranked_artefacts,
        sample_case_metadata,
        timings,
    )
    second = exporter.export(
        sample_artefact_set,
        sample_ranked_artefacts,
        sample_case_metadata,
        timings,
    )

    # Assert
    assert first.integrity_hash == second.integrity_hash


def test_export_artefact_data_matches_ranked_count(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify exported artefact_data length matches ranked artefacts."""
    # Arrange
    exporter = _exporter()

    # Act
    report = exporter.export(
        sample_artefact_set,
        sample_ranked_artefacts,
        sample_case_metadata,
        {"acquisition_s": 0.1, "parsing_s": 0.1, "triage_s": 0.1, "reporting_s": 0.1},
    )

    # Assert
    assert len(report.artefact_data) == len(sample_ranked_artefacts)
