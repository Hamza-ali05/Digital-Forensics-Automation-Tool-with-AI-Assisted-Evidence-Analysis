"""Unit tests for dual-output report builder."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from dfat.core.enums import HashAlgorithm
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler
from dfat.reporting.report_builder import DualOutputReportBuilder


def _builder(mock_audit_logger: MagicMock) -> DualOutputReportBuilder:
    """Construct a DualOutputReportBuilder with real exporters and mock repo."""
    schema = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "dfat"
        / "reporting"
        / "templates"
        / "report_schema.json"
    )
    template_dir = schema.parent
    return DualOutputReportBuilder(
        json_exporter=StructuredJSONExporter(schema, HashAlgorithm.SHA256),
        narrative_assembler=NarrativeAssembler(template_dir),
        report_repo=MagicMock(),
        audit_logger=mock_audit_logger,
    )


def test_build_complete_report_includes_json_and_narrative(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify dual-output assembly includes both report layers."""
    # Arrange
    builder = _builder(mock_audit_logger)

    # Act
    report = builder.build_complete_report(
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        ranked_artefacts=sample_ranked_artefacts,
        summary_text="Investigative summary fixture.",
        llm_model="RuleBasedFallback",
        generation_params={"use_fallback": True},
        stage_timings={
            "acquisition_s": 0.5,
            "parsing_s": 0.5,
            "triage_s": 0.5,
            "reporting_s": 0.2,
        },
    )

    # Assert
    assert report.json_report.integrity_hash
    assert report.narrative_report.summary_text
    assert report.case.case_name == sample_case_metadata.case_name


def test_build_complete_report_persists_via_repository(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify the report builder saves through the report repository."""
    # Arrange
    builder = _builder(mock_audit_logger)

    # Act
    report = builder.build_complete_report(
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        ranked_artefacts=sample_ranked_artefacts,
        summary_text="Summary",
        llm_model="Mock",
        generation_params={},
        stage_timings={"acquisition_s": 0.1, "parsing_s": 0.1, "triage_s": 0.1, "reporting_s": 0.1},
    )

    # Assert
    builder._report_repo.save.assert_called()  # type: ignore[attr-defined]
    assert report.report_id


def test_build_complete_report_records_audit_entry(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify report assembly emits an audit trail entry."""
    # Arrange
    builder = _builder(mock_audit_logger)

    # Act
    builder.build_complete_report(
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        ranked_artefacts=sample_ranked_artefacts,
        summary_text="Summary",
        llm_model="Mock",
        generation_params={},
        stage_timings={"acquisition_s": 0.1, "parsing_s": 0.1, "triage_s": 0.1, "reporting_s": 0.1},
    )

    # Assert
    mock_audit_logger.log_action.assert_called()
