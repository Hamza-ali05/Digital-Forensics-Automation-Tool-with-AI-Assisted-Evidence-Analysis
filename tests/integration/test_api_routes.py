"""Integration tests for FastAPI routes via TestClient."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from dfat.core.enums import EvidenceType, HashAlgorithm
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.evaluation import BenchmarkResult
from dfat.core.models.pipeline import PipelineState, StageResult
from dfat.core.enums import PipelineStage
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport


def test_list_evidence_returns_empty_list(app_client: TestClient) -> None:
    """Verify GET /api/v1/evidence returns an empty list initially."""
    # Arrange / Act
    response = app_client.get("/api/v1/evidence")

    # Assert
    assert response.status_code == 200
    assert response.json() == []


def test_register_evidence_returns_201(
    app_client: TestClient,
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify POST /api/v1/evidence registers a disk image and returns 201."""
    # Arrange
    evidence_file = tmp_path / "api_sample.dd"
    evidence_file.write_bytes(b"API-EVIDENCE")
    evidence = EvidenceImage(
        evidence_id="ev-api-1",
        file_path=evidence_file,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="c" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=evidence_file.stat().st_size,
        case=sample_case_metadata,
    )
    container = app_client.app.state.container
    handler = MagicMock()
    handler.load_image.return_value = evidence
    container.forensic_engine.image_handler.override(handler)

    try:
        # Act
        response = app_client.post(
            "/api/v1/evidence",
            json={
                "file_path": str(evidence_file),
                "case_name": sample_case_metadata.case_name,
                "investigator": sample_case_metadata.investigator,
                "description": sample_case_metadata.description,
                "evidence_type": "disk_image",
            },
        )

        # Assert
        assert response.status_code == 201
        body = response.json()
        assert body["evidence_id"] == "ev-api-1"
        assert body["evidence_type"] == "disk_image"
    finally:
        container.forensic_engine.image_handler.reset_override()


def test_get_evidence_returns_404_for_unknown_id(app_client: TestClient) -> None:
    """Verify GET /api/v1/evidence/{id} returns 404 for missing evidence."""
    # Arrange / Act
    response = app_client.get("/api/v1/evidence/does-not-exist")

    # Assert
    assert response.status_code == 404
    assert response.json()["error_type"] == "EvidenceNotFoundError"


def test_run_analysis_returns_202(
    app_client: TestClient,
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify POST /api/v1/analysis returns pipeline status with 202."""
    # Arrange
    state = PipelineState(
        case=sample_case_metadata,
        current_stage=PipelineStage.PARSING,
        stage_results={
            "parsing": StageResult(
                stage=PipelineStage.PARSING,
                success=True,
                duration_seconds=0.1,
                output_data={"artefact_count": 0},
            )
        },
    )
    orchestrator = MagicMock()
    orchestrator.start_pipeline.return_value = state
    container = app_client.app.state.container
    container.pipeline.pipeline_orchestrator.override(orchestrator)

    try:
        # Act
        response = app_client.post(
            "/api/v1/analysis",
            json={
                "evidence_id": "ev-api-1",
                "mode": "parse-only",
                "use_fallback": True,
            },
        )

        # Assert
        assert response.status_code == 202
        body = response.json()
        assert body["pipeline_id"] == state.pipeline_id
        assert body["current_stage"] == "parsing"
    finally:
        container.pipeline.pipeline_orchestrator.reset_override()


def test_get_analysis_returns_404_for_unknown_pipeline(app_client: TestClient) -> None:
    """Verify GET /api/v1/analysis/{id} returns 404 when pipeline is missing."""
    # Arrange
    orchestrator = MagicMock()
    orchestrator.get_pipeline_state.return_value = None
    container = app_client.app.state.container
    container.pipeline.pipeline_orchestrator.override(orchestrator)

    try:
        # Act
        response = app_client.get("/api/v1/analysis/missing-pipeline")

        # Assert
        assert response.status_code == 404
    finally:
        container.pipeline.pipeline_orchestrator.reset_override()


def test_get_report_returns_404_for_unknown_report(app_client: TestClient) -> None:
    """Verify GET /api/v1/reports/{id} returns 404 for missing reports."""
    # Arrange / Act
    response = app_client.get("/api/v1/reports/missing-report")

    # Assert
    assert response.status_code == 404


def test_get_report_json_and_narrative(
    app_client: TestClient,
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify report JSON and narrative sub-routes return content."""
    # Arrange
    report = ForensicReport(
        report_id="rep-1",
        case=sample_case_metadata,
        json_report=JSONReport(
            report_id="json-1",
            evidence_id="ev-1",
            artefact_data=[],
            integrity_hash="d" * 64,
        ),
        narrative_report=NarrativeReport(
            report_id="narr-1",
            evidence_id="ev-1",
            summary_text="Narrative body",
            llm_model_used="Mock",
            generation_parameters={},
        ),
        pipeline_duration_seconds=1.5,
        stage_timings={},
    )
    repo = MagicMock()
    repo.get.return_value = report
    container = app_client.app.state.container
    container.repositories.report_repo.override(repo)

    try:
        # Act
        summary = app_client.get("/api/v1/reports/rep-1")
        json_resp = app_client.get("/api/v1/reports/rep-1/json")
        narrative = app_client.get("/api/v1/reports/rep-1/narrative")

        # Assert
        assert summary.status_code == 200
        assert summary.json()["report_id"] == "rep-1"
        assert json_resp.status_code == 200
        assert json_resp.json()["integrity_hash"] == "d" * 64
        assert narrative.status_code == 200
        assert narrative.text == "Narrative body"
    finally:
        container.repositories.report_repo.reset_override()


def test_evaluation_benchmark_and_results_list(app_client: TestClient) -> None:
    """Verify benchmark POST and results GET endpoints."""
    # Arrange
    result = BenchmarkResult(
        benchmark_id="bench-1",
        dataset_name="sample",
        precision=1.0,
        recall=1.0,
        f1_score=1.0,
        time_to_triage_seconds=1.0,
        artefacts_expected=2,
        artefacts_recovered=2,
        false_positives=0,
        false_negatives=0,
    )
    orchestrator = MagicMock()
    orchestrator.run_benchmark.return_value = result
    orchestrator.list_benchmark_results.return_value = [result]
    container = app_client.app.state.container
    container.pipeline.pipeline_orchestrator.override(orchestrator)

    try:
        # Act
        created = app_client.post(
            "/api/v1/evaluation/benchmark",
            json={
                "evidence_id": "ev-1",
                "ground_truth_path": "/tmp/gt.json",
                "dataset_name": "sample",
            },
        )
        listed = app_client.get("/api/v1/evaluation/results")

        # Assert
        assert created.status_code == 200
        assert created.json()["benchmark_id"] == "bench-1"
        assert listed.status_code == 200
        assert len(listed.json()) == 1
    finally:
        container.pipeline.pipeline_orchestrator.reset_override()


def test_analysis_rejects_invalid_mode(app_client: TestClient) -> None:
    """Verify AnalysisRunRequest rejects modes outside the allowed pattern."""
    # Arrange / Act
    response = app_client.post(
        "/api/v1/analysis",
        json={"evidence_id": "ev-1", "mode": "invalid-mode"},
    )

    # Assert
    assert response.status_code == 422
