"""Integration tests for end-to-end reporting pipeline (Prompt 6.20)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.core.enums import HashAlgorithm
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.case import Case
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import ForensicReport
from dfat.reporting.exporters.html_exporter import HTMLReportExporter
from dfat.reporting.exporters.json_file_exporter import JSONFileExporter
from dfat.reporting.exporters.pdf_exporter import PDFReportExporter
from dfat.reporting.integrity import ReportIntegrityVerifier
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler
from dfat.reporting.report_builder import DualOutputReportBuilder
from dfat.reporting.reproducibility import ReproducibilityVerifier
from dfat.reporting.schema import ReportSchemaValidator
from dfat.services.audit_service import AuditService


def _template_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dfat"
        / "reporting"
        / "templates"
    )


def _builder() -> DualOutputReportBuilder:
    report_repo = MagicMock()
    report_repo.save = MagicMock(return_value="saved")
    audit_service = MagicMock(spec=AuditService)
    audit_service.log_action = AsyncMock(return_value=None)
    return DualOutputReportBuilder(
        json_exporter=StructuredJSONExporter(
            schema_validator=ReportSchemaValidator(),
            hash_algorithm=HashAlgorithm.SHA256,
        ),
        narrative_assembler=NarrativeAssembler(_template_dir()),
        integrity_verifier=ReportIntegrityVerifier(),
        report_repo=report_repo,
        audit_service=audit_service,
    )


def _stage_timings() -> dict[str, float]:
    return {
        "acquisition_seconds": 1.0,
        "parsing_seconds": 2.0,
        "triage_seconds": 3.0,
        "reporting_seconds": 0.5,
    }


def _case_from_metadata(metadata: CaseMetadata) -> Case:
    return Case(metadata=metadata, evidence_ids=[], tags=[], lead_investigator_id="user-1")


def test_full_report_generation(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
    tmp_path: Path,
) -> None:
    """Verify artefacts → JSON + narrative → PDF + HTML export path."""
    builder = _builder()
    summary = SummaryResult(
        full_text="Full narrative body for integration.",
        executive_summary="Executive summary of findings.",
        key_findings=["Finding one", "Finding two"],
        timeline_narrative="T0 acquire; T1 triage.",
        iocs_identified=["evil.exe"],
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
        stage_timings=_stage_timings(),
        confidence=0.8,
        evidence_hash="e" * 64,
        pipeline_job_id="job-int-1",
        user_id="analyst-1",
    )
    assert isinstance(report, ForensicReport)
    assert report.json_report.integrity_hash
    assert "DISCLAIMER:" in report.narrative_report.summary_text

    pdf_path = PDFReportExporter(tmp_path).export(report)
    html_path = HTMLReportExporter(tmp_path, _template_dir()).export(
        report, _case_from_metadata(sample_case_metadata)
    )
    json_path = JSONFileExporter().export(report.json_report, tmp_path)

    assert pdf_path.exists()
    assert html_path.exists() and html_path.suffix == ".html"
    assert json_path.exists() and json_path.suffix == ".json"
    assert "<style>" in html_path.read_text(encoding="utf-8")


def test_report_integrity_round_trip(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
    tmp_path: Path,
) -> None:
    """Verify generate → verify → passes integrity checks."""
    report = _builder().build_complete_report(
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        ranked_artefacts=sample_ranked_artefacts,
        summary_text="Integrity round-trip summary.",
        llm_model="RuleBasedFallback",
        generation_params={"use_fallback": True},
        stage_timings=_stage_timings(),
        confidence=0.6,
        evidence_hash="f" * 64,
    )
    document = {
        "schema_version": report.json_report.schema_version,
        "report_id": report.json_report.report_id,
        "evidence_id": report.json_report.evidence_id,
        "case_metadata": {
            "case_id": sample_case_metadata.case_id,
            "case_name": sample_case_metadata.case_name,
            "investigator": sample_case_metadata.investigator,
        },
        "generated_at": report.json_report.generated_at.isoformat(),
        "integrity_hash": report.json_report.integrity_hash,
        "pipeline_stage_timings": _stage_timings(),
        "artefacts": report.json_report.artefact_data,
        "summary_statistics": {
            "total_artefacts": len(report.json_report.artefact_data),
            "by_category": {},
            "by_suspicion_level": {},
        },
        "ai_metadata": {
            "model_used": "RuleBasedFallback",
            "analysis_mode": "rule_based",
            "confidence_score": 0.6,
            "prompt_version": "1.0.0",
            "disclaimer": "Advisory.",
        },
    }
    path = tmp_path / "round_trip.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    result = ReportIntegrityVerifier().verify_report_file(path)
    assert result.is_valid is True
    assert result.integrity_hash_match is True


def test_reproducibility(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify two reporting runs on identical inputs produce identical hashes."""
    builder = _builder()
    kwargs = {
        "case": sample_case_metadata,
        "artefact_set": sample_artefact_set,
        "ranked_artefacts": sample_ranked_artefacts,
        "summary_text": "Reproducibility summary.",
        "llm_model": "RuleBasedFallback",
        "generation_params": {"use_fallback": True},
        "stage_timings": _stage_timings(),
        "confidence": 0.7,
        "evidence_hash": "aa" * 32,
    }
    first = builder.build_complete_report(**kwargs)
    second = builder.build_complete_report(**kwargs)
    assert first.json_report.integrity_hash == second.json_report.integrity_hash

    report_a = {
        "integrity_hash": first.json_report.integrity_hash,
        "artefacts": first.json_report.artefact_data,
    }
    report_b = {
        "integrity_hash": second.json_report.integrity_hash,
        "artefacts": second.json_report.artefact_data,
    }
    result = ReproducibilityVerifier().compare_reports(report_a, report_b)
    assert result.is_reproducible is True
    assert result.hashes_match is True
