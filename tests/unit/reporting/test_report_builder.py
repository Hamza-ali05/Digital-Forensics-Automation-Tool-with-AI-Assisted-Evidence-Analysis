"""Unit tests for dual-output report builder (Prompt 6.5)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.core.enums import HashAlgorithm
from dfat.core.interfaces.reporter import IReportGenerator
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import ForensicReport
from dfat.reporting.integrity import ReportIntegrityVerifier
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler
from dfat.reporting.report_builder import DualOutputReportBuilder
from dfat.reporting.schema import ReportSchemaValidator
from dfat.services.audit_service import AuditService


def _template_dir() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "src"
        / "dfat"
        / "reporting"
        / "templates"
    )


def _builder() -> tuple[DualOutputReportBuilder, MagicMock, AsyncMock]:
    """Construct a builder with real exporters and mocked repo/audit."""
    report_repo = MagicMock()
    report_repo.save = MagicMock(return_value="saved")
    audit_service = MagicMock(spec=AuditService)
    audit_service.log_action = AsyncMock(return_value=None)
    builder = DualOutputReportBuilder(
        json_exporter=StructuredJSONExporter(
            schema_validator=ReportSchemaValidator(
                schema_path=_template_dir() / "report_schema.json"
            ),
            hash_algorithm=HashAlgorithm.SHA256,
        ),
        narrative_assembler=NarrativeAssembler(_template_dir()),
        integrity_verifier=ReportIntegrityVerifier(),
        report_repo=report_repo,
        audit_service=audit_service,
    )
    return builder, report_repo, audit_service


def test_builder_is_ireport_generator() -> None:
    """Verify DualOutputReportBuilder implements IReportGenerator."""
    builder, _, _ = _builder()
    assert isinstance(builder, IReportGenerator)
    assert issubclass(DualOutputReportBuilder, IReportGenerator)


def test_build_complete_report_includes_json_and_narrative(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify dual-output assembly includes both report layers."""
    builder, report_repo, audit_service = _builder()
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
        confidence=0.6,
        evidence_hash="abc123",
        pipeline_job_id="job-1",
        user_id="analyst-1",
    )

    assert isinstance(report, ForensicReport)
    assert report.json_report.integrity_hash
    assert report.narrative_report.summary_text
    assert "DISCLAIMER:" in report.narrative_report.summary_text
    assert report.case.case_name == sample_case_metadata.case_name
    assert report.audit_metadata.get("generated_by_user_id") == "analyst-1"
    assert report.audit_metadata.get("pipeline_job_id") == "job-1"
    asyncio.run(builder.persist_report(report))
    report_repo.save.assert_called_once()
    assert audit_service.log_action.await_count >= 3


def test_build_complete_report_with_summary_result(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify build_complete_report accepts a SummaryResult object."""
    builder, report_repo, _ = _builder()
    summary = SummaryResult(
        full_text="Full text",
        executive_summary="Executive summary for case.",
        key_findings=["Finding one"],
        iocs_identified=["ioc.exe"],
        recommended_actions=["Preserve evidence"],
        model_used="llama3",
        prompt_version="1.0.0",
        confidence_score=0.8,
    )
    report = builder.build_complete_report(
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        ranked=sample_ranked_artefacts,
        summary_result=summary,
        llm_model="llama3",
        generation_params={},
        stage_timings={"acquisition_seconds": 1.0},
        confidence=0.8,
        pipeline_job_id="job-2",
        user_id="user-2",
    )
    assert isinstance(report, ForensicReport)
    assert "Executive summary for case." in report.narrative_report.summary_text
    asyncio.run(builder.persist_report(report))
    report_repo.save.assert_called_once()


def test_build_complete_report_persists_via_repository(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify the report builder saves through the report repository."""
    builder, report_repo, _ = _builder()
    report = builder.build_complete_report(
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        ranked_artefacts=sample_ranked_artefacts,
        summary_text="Summary",
        llm_model="Mock",
        generation_params={},
        stage_timings={
            "acquisition_s": 0.1,
            "parsing_s": 0.1,
            "triage_s": 0.1,
            "reporting_s": 0.1,
        },
    )
    asyncio.run(builder.persist_report(report))
    report_repo.save.assert_called()
    saved = report_repo.save.call_args.args[0]
    assert isinstance(saved, ForensicReport)
    assert saved.report_id == report.report_id


def test_build_complete_report_records_audit_entries(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify JSON, narrative, and full-report audit actions are logged."""
    builder, _, audit_service = _builder()
    builder.build_complete_report(
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        ranked_artefacts=sample_ranked_artefacts,
        summary_text="Summary",
        llm_model="Mock",
        generation_params={},
        stage_timings={
            "acquisition_s": 0.1,
            "parsing_s": 0.1,
            "triage_s": 0.1,
            "reporting_s": 0.1,
        },
        user_id="auditor",
    )
    actions = [call.kwargs["action"] for call in audit_service.log_action.await_args_list]
    assert "JSON_REPORT_GENERATED" in actions
    assert "NARRATIVE_GENERATED" in actions
    assert "REPORT_GENERATED" in actions


# Prompt 6.20 named coverage aliases
test_implements_ireport_generator = test_builder_is_ireport_generator
test_build_complete_produces_forensic_report = test_build_complete_report_includes_json_and_narrative
test_audit_entries_logged = test_build_complete_report_records_audit_entries
test_json_and_narrative_both_present = test_build_complete_report_includes_json_and_narrative

