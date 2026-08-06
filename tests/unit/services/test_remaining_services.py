"""Unit tests for remaining application services with mocked dependencies."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.pipeline import AuditEntry, PipelineState
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.core.enums import HashAlgorithm
from dfat.services.analysis_service import AnalysisService
from dfat.services.evaluation_service import EvaluationService
from dfat.services.evidence_service import EvidenceService
from dfat.services.report_service import ReportService


@pytest.mark.asyncio
async def test_evidence_service_register_and_get(tmp_path: Path) -> None:
    """EvidenceService registers via handler and persists metadata."""
    # Arrange
    path = tmp_path / "sample.dd"
    path.write_bytes(b"data")
    evidence = EvidenceImage(
        evidence_id="ev-svc-1",
        file_path=path,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=4,
        case=CaseMetadata(case_id="c1", case_name="C", investigator="I"),
    )
    evidence_repo = AsyncMock()
    evidence_repo.get.return_value = evidence
    evidence_repo.list_all.return_value = [evidence]
    evidence_repo.delete.return_value = True
    audit_repo = AsyncMock(get_latest_entry_number=AsyncMock(return_value=0))
    disk = MagicMock()
    disk.load_image.return_value = evidence
    integrity = MagicMock()
    integrity.verify_integrity.return_value = True
    service = EvidenceService(
        evidence_repo=evidence_repo,
        integrity_checker=integrity,
        disk_handler=disk,
        memory_handler=MagicMock(),
        audit_repo=audit_repo,
        storage=MagicMock(base_dir=tmp_path),
    )

    # Act
    registered = await service.register_evidence(
        path,
        "Case",
        "Inv",
        EvidenceType.DISK_IMAGE,
        None,
        "user-1",
    )
    loaded = await service.get_evidence("ev-svc-1")
    listed = await service.list_evidence()
    ok = await service.verify_evidence_integrity("ev-svc-1")
    deleted = await service.delete_evidence("ev-svc-1", "user-1")

    # Assert
    assert registered.evidence_id == "ev-svc-1"
    assert loaded.evidence_id == "ev-svc-1"
    assert len(listed) == 1
    assert ok is True
    assert deleted is True
    evidence_repo.save.assert_awaited()


@pytest.mark.asyncio
async def test_report_service_getters() -> None:
    """ReportService returns report components from the repository."""
    # Arrange
    case = CaseMetadata(case_id="c1", case_name="C", investigator="I")
    report = ForensicReport(
        report_id="rep-1",
        case=case,
        json_report=JSONReport(
            report_id="j1",
            evidence_id="ev-1",
            integrity_hash="b" * 64,
        ),
        narrative_report=NarrativeReport(
            report_id="n1",
            evidence_id="ev-1",
            summary_text="text",
            llm_model_used="mock",
        ),
        pipeline_duration_seconds=1.0,
    )
    report_repo = AsyncMock()
    report_repo.get.return_value = report
    report_repo.list_all.return_value = [report]
    report_repo.get_by_case.return_value = [report]
    service = ReportService(report_repo, AsyncMock())

    # Act
    full = await service.get_report("rep-1")
    json_part = await service.get_json_report("rep-1")
    narrative = await service.get_narrative_report("rep-1")
    listed = await service.list_reports()
    by_case = await service.get_reports_by_case("c1")

    # Assert
    assert full.report_id == "rep-1"
    assert json_part.integrity_hash == "b" * 64
    assert narrative.summary_text == "text"
    assert listed and by_case


@pytest.mark.asyncio
async def test_analysis_service_status_and_parse(
    sample_artefact_set: ArtefactSet,
    sample_evidence_image: EvidenceImage,
) -> None:
    """AnalysisService coordinates parse-only runs and status lookups."""
    # Arrange
    evidence_repo = AsyncMock()
    evidence_repo.get.return_value = sample_evidence_image
    artefact_repo = AsyncMock()
    report_repo = AsyncMock()
    audit_repo = AsyncMock(get_latest_entry_number=AsyncMock(return_value=0))
    integrity = MagicMock()
    integrity.verify_integrity.return_value = True
    pipeline = MagicMock()
    pipeline.run_parse_only.return_value = sample_artefact_set
    state = PipelineState(
        case=sample_evidence_image.case,
        current_stage=PipelineStage.PARSING,
    )
    pipeline.get_pipeline_state.return_value = state
    service = AnalysisService(
        pipeline_orchestrator=pipeline,
        evidence_repo=evidence_repo,
        artefact_repo=artefact_repo,
        report_repo=report_repo,
        audit_repo=audit_repo,
        integrity_checker=integrity,
    )

    # Act
    artefacts = await service.run_parse_only(sample_evidence_image.evidence_id, "user-1")
    status = await service.get_analysis_status(state.pipeline_id)

    # Assert
    assert artefacts.total_count == sample_artefact_set.total_count
    assert status.pipeline_id == state.pipeline_id
    artefact_repo.save.assert_awaited()


@pytest.mark.asyncio
async def test_evaluation_service_benchmark_and_usability(
    sample_artefact_set: ArtefactSet,
) -> None:
    """EvaluationService persists benchmarks and analyses usability."""
    # Arrange
    result = BenchmarkResult(
        benchmark_id="b1",
        dataset_name="dfrws",
        precision=1.0,
        recall=1.0,
        f1_score=1.0,
        time_to_triage_seconds=1.0,
        artefacts_expected=1,
        artefacts_recovered=1,
        false_positives=0,
        false_negatives=0,
    )
    response = UsabilityResponse(
        response_id="u1",
        participant_id="p1",
        usefulness_rating=5,
        accuracy_rating=4,
        clarity_rating=5,
    )
    benchmark_repo = AsyncMock()
    benchmark_repo.list_all.return_value = [result]
    usability_repo = AsyncMock()
    usability_repo.save.return_value = "u1"
    usability_repo.get_all_responses.return_value = [response]
    comparator = MagicMock()
    comparator.compare.return_value = result
    loader = MagicMock()
    loader.load.return_value = {"dataset_name": "dfrws", "artefacts": []}
    audit_repo = AsyncMock(get_latest_entry_number=AsyncMock(return_value=0))
    service = EvaluationService(
        benchmark_repo=benchmark_repo,
        usability_repo=usability_repo,
        benchmark_comparator=comparator,
        ground_truth_loader=loader,
        audit_repo=audit_repo,
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 0, 1, tzinfo=UTC)

    # Act
    bench = await service.run_benchmark(
        "ev-1",
        "/tmp/gt.json",
        "dfrws",
        sample_artefact_set,
        start,
        end,
        "user-1",
    )
    saved_id = await service.submit_usability_response(response)
    listed = await service.get_benchmark_results()
    analysis = await service.get_usability_analysis()

    # Assert
    assert bench.benchmark_id == "b1"
    assert saved_id == "u1"
    assert listed
    assert analysis["response_count"] == 1
