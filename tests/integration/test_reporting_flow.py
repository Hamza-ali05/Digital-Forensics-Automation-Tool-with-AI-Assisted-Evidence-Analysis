"""Reporting flow integration tests (Prompt 9.4)."""

from __future__ import annotations

import copy
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
    return Case(
        metadata=metadata,
        evidence_ids=[],
        tags=[],
        lead_investigator_id="user-1",
    )


def _summary() -> SummaryResult:
    return SummaryResult(
        full_text="Full narrative body for reporting flow.",
        executive_summary="Executive summary of findings.",
        key_findings=["Finding one", "Finding two"],
        timeline_narrative="T0 acquire; T1 triage.",
        iocs_identified=["evil.exe"],
        recommended_actions=["Preserve evidence"],
        model_used="RuleBasedFallback",
        prompt_version="1.0.0",
        confidence_score=0.8,
    )


def _build_report(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> ForensicReport:
    return _builder().build_complete_report(
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        ranked=sample_ranked_artefacts,
        summary_result=_summary(),
        llm_model="RuleBasedFallback",
        generation_params={"use_fallback": True},
        stage_timings=_stage_timings(),
        confidence=0.8,
        evidence_hash="e" * 64,
        pipeline_job_id="job-report-flow",
        user_id="analyst-1",
    )


def _document_from_report(
    report: ForensicReport, sample_case_metadata: CaseMetadata
) -> dict:
    return {
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
            "confidence_score": 0.8,
            "prompt_version": "1.0.0",
            "disclaimer": "Advisory.",
        },
    }


def test_report_generation_and_export(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
    tmp_path: Path,
) -> None:
    """Pipeline-style report → PDF / HTML / JSON exports are valid files."""
    report = _build_report(
        sample_artefact_set, sample_ranked_artefacts, sample_case_metadata
    )
    assert isinstance(report, ForensicReport)
    assert report.json_report.integrity_hash

    pdf_path = PDFReportExporter(tmp_path).export(report)
    html_path = HTMLReportExporter(tmp_path, _template_dir()).export(
        report, _case_from_metadata(sample_case_metadata)
    )
    json_path = JSONFileExporter().export(report.json_report, tmp_path)

    assert pdf_path.exists() and pdf_path.stat().st_size > 0
    assert html_path.exists() and "<style>" in html_path.read_text(encoding="utf-8")
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload.get("integrity_hash") or payload.get("evidence_id")


def test_report_reproducibility(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Two pipeline reporting runs on identical inputs share artefact data hashes."""
    kwargs = {
        "case": sample_case_metadata,
        "artefact_set": sample_artefact_set,
        "ranked": sample_ranked_artefacts,
        "summary_text": "Reproducibility summary for flow test.",
        "llm_model": "RuleBasedFallback",
        "generation_params": {"use_fallback": True},
        "stage_timings": _stage_timings(),
        "confidence": 0.7,
        "evidence_hash": "aa" * 32,
    }
    first = _builder().build_complete_report(**kwargs)
    second = _builder().build_complete_report(**kwargs)

    assert first.json_report.integrity_hash == second.json_report.integrity_hash
    result = ReproducibilityVerifier().compare_reports(
        {
            "integrity_hash": first.json_report.integrity_hash,
            "artefacts": first.json_report.artefact_data,
        },
        {
            "integrity_hash": second.json_report.integrity_hash,
            "artefacts": second.json_report.artefact_data,
        },
    )
    assert result.is_reproducible is True
    assert result.hashes_match is True


def test_report_integrity_verification(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
    tmp_path: Path,
) -> None:
    """Generate → verify passes; tamper artefact data → verify fails."""
    report = _build_report(
        sample_artefact_set, sample_ranked_artefacts, sample_case_metadata
    )
    document = _document_from_report(report, sample_case_metadata)
    clean_path = tmp_path / "clean_report.json"
    clean_path.write_text(json.dumps(document), encoding="utf-8")

    clean = ReportIntegrityVerifier().verify_report_file(clean_path)
    assert clean.is_valid is True
    assert clean.integrity_hash_match is True

    tampered = copy.deepcopy(document)
    if tampered["artefacts"]:
        first = tampered["artefacts"][0]
        if isinstance(first, dict):
            first["raw_data"] = {"tampered": True}
        else:
            tampered["artefacts"][0] = {"tampered": True}
    else:
        tampered["artefacts"] = [{"artefact_id": "x", "raw_data": {"t": 1}}]
    tampered_path = tmp_path / "tampered_report.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")

    broken = ReportIntegrityVerifier().verify_report_file(tampered_path)
    assert broken.is_valid is False
    assert broken.integrity_hash_match is False
