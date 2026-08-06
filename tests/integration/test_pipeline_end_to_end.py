"""Integration tests for end-to-end pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.core.enums import EvidenceType, HashAlgorithm
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.forensic_engine.normalizer import ArtefactNormalizer
from dfat.forensic_engine.orchestrator import ForensicOrchestrator
from dfat.pipeline import PipelineOrchestrator
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler
from dfat.reporting.report_builder import DualOutputReportBuilder


def _pipeline(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    mock_audit_logger: MagicMock,
    artefact_set: ArtefactSet,
) -> tuple[PipelineOrchestrator, Path]:
    """Build a PipelineOrchestrator with mocked forensic acquisition/parsing."""
    evidence_path = tmp_path / "sample.dd"
    evidence_path.write_bytes(b"DFAT-E2E")
    evidence = EvidenceImage(
        evidence_id=artefact_set.evidence_id,
        file_path=evidence_path,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=evidence_path.stat().st_size,
        case=sample_case_metadata,
    )

    disk_handler = MagicMock()
    disk_handler.load_image.return_value = evidence
    parser = MagicMock()
    parser.parser_name = "MockParser"
    parser.supported_evidence_types.return_value = [EvidenceType.DISK_IMAGE]
    parser.parse.return_value = artefact_set

    integrity = MagicMock()
    integrity.verify_integrity.return_value = True
    forensic = ForensicOrchestrator(
        parsers=[parser],  # type: ignore[arg-type]
        normalizer=ArtefactNormalizer(),
        integrity_checker=integrity,
        disk_handler=disk_handler,
        memory_handler=MagicMock(),
        audit_logger=mock_audit_logger,
    )

    schema = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dfat"
        / "reporting"
        / "templates"
        / "report_schema.json"
    )
    report_builder = DualOutputReportBuilder(
        json_exporter=StructuredJSONExporter(schema, HashAlgorithm.SHA256),
        narrative_assembler=NarrativeAssembler(schema.parent),
        report_repo=MagicMock(),
        audit_logger=mock_audit_logger,
    )

    llm = MagicMock()
    llm.analyzer_name = "MockLLM"
    llm.is_available.return_value = False
    llm.analyze.side_effect = RuntimeError("LLM unavailable")
    llm.summarize.side_effect = RuntimeError("LLM unavailable")

    orchestrator = PipelineOrchestrator(
        forensic_orchestrator=forensic,
        analyzer=llm,
        fallback_analyzer=RuleBasedAnalyzer(),
        report_builder=report_builder,
        evidence_repo=MagicMock(),
        report_repo=MagicMock(),
        ground_truth_loader=GroundTruthLoader(tmp_path),
        benchmark_comparator=BenchmarkComparator(
            MetricsCalculator(),
            mock_audit_logger,
            {"precision_min": 0.0, "recall_min": 0.0, "f1_min": 0.0},
        ),
        audit_logger=mock_audit_logger,
    )
    return orchestrator, evidence_path


def test_run_full_pipeline_completes_all_stages_with_fallback(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify full pipeline runs all stages and falls back when LLM fails."""
    # Arrange
    orchestrator, evidence_path = _pipeline(
        tmp_path,
        sample_case_metadata,
        mock_audit_logger,
        sample_artefact_set,
    )

    # Act
    report = orchestrator.run_full_pipeline(
        evidence_path,
        sample_case_metadata,
        use_fallback=True,
    )

    # Assert
    assert report.report_id
    assert report.json_report.integrity_hash
    assert report.narrative_report.summary_text
    assert "acquisition_s" in report.stage_timings
    assert "parsing_s" in report.stage_timings
    assert "triage_s" in report.stage_timings
    assert "reporting_s" in report.stage_timings


def test_run_parse_only_returns_artefact_set(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify parse-only mode returns a normalised artefact set."""
    # Arrange
    orchestrator, evidence_path = _pipeline(
        tmp_path,
        sample_case_metadata,
        mock_audit_logger,
        sample_artefact_set,
    )

    # Act
    artefact_set = orchestrator.run_parse_only(evidence_path, sample_case_metadata)

    # Assert
    assert artefact_set.total_count == sample_artefact_set.total_count


def test_run_triage_only_ranks_artefacts(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify triage-only mode returns ranked artefacts via fallback."""
    # Arrange
    orchestrator, _ = _pipeline(
        tmp_path,
        sample_case_metadata,
        mock_audit_logger,
        sample_artefact_set,
    )

    # Act
    ranked = orchestrator.run_triage_only(sample_artefact_set, use_fallback=True)

    # Assert
    assert len(ranked) == sample_artefact_set.total_count
    assert all(item.suspicion_level is not None for item in ranked)


def test_pipeline_state_marks_evaluation_stage(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify full pipeline records all five stage results including evaluation."""
    # Arrange
    orchestrator, evidence_path = _pipeline(
        tmp_path,
        sample_case_metadata,
        mock_audit_logger,
        sample_artefact_set,
    )

    # Act
    report = orchestrator.run_full_pipeline(
        evidence_path,
        sample_case_metadata,
        use_fallback=True,
    )
    pipeline_id = next(
        pid for pid, rid in orchestrator._pipeline_reports.items() if rid == report.report_id
    )
    state = orchestrator.get_pipeline_state(pipeline_id)

    # Assert
    assert state is not None
    assert state.is_complete is True
    assert "evaluation" in state.stage_results
