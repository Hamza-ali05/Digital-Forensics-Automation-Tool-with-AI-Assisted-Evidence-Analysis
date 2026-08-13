"""Integration tests for FastAPI routes via TestClient."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from dfat.core.enums import EvidenceType, HashAlgorithm, PipelineStage
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.evaluation import BenchmarkResult
from dfat.core.models.pipeline import PipelineState, StageResult
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport


def _auth(client: TestClient) -> dict[str, str]:
    """Return Authorization headers for the seeded analyst token."""
    return {"Authorization": f"Bearer {client.analyst_token}"}  # type: ignore[attr-defined]


def _admin_auth(client: TestClient) -> dict[str, str]:
    """Return Authorization headers for the seeded admin token."""
    return {"Authorization": f"Bearer {client.admin_token}"}  # type: ignore[attr-defined]


def test_list_evidence_returns_empty_list(app_client: TestClient) -> None:
    """Verify GET /api/v1/evidence returns an empty list initially."""
    # Arrange / Act
    response = app_client.get("/api/v1/evidence", headers=_auth(app_client))

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
    service = AsyncMock()
    service.register_evidence = AsyncMock(return_value=evidence)
    container.services.evidence_service.override(service)

    try:
        # Act
        response = app_client.post(
            "/api/v1/evidence",
            headers=_admin_auth(app_client),
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
        container.services.evidence_service.reset_override()


def test_get_evidence_returns_404_for_unknown_id(app_client: TestClient) -> None:
    """Verify GET /api/v1/evidence/{id} returns 404 for missing evidence."""
    # Arrange
    from dfat.core.exceptions import EvidenceNotFoundError

    container = app_client.app.state.container
    service = AsyncMock()
    service.get_evidence = AsyncMock(
        side_effect=EvidenceNotFoundError("Evidence not found: does-not-exist")
    )
    container.services.evidence_service.override(service)

    try:
        # Act
        response = app_client.get(
            "/api/v1/evidence/does-not-exist",
            headers=_auth(app_client),
        )

        # Assert
        assert response.status_code == 404
        assert response.json()["error_type"] == "EvidenceNotFoundError"
    finally:
        container.services.evidence_service.reset_override()


def test_run_analysis_returns_202(
    app_client: TestClient,
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify POST /api/v1/analysis returns pipeline status with 202."""
    # Arrange
    container = app_client.app.state.container
    service = AsyncMock()
    service.run_parse_only = AsyncMock(return_value=MagicMock())
    container.services.analysis_service.override(service)

    try:
        # Act
        response = app_client.post(
            "/api/v1/analysis",
            headers=_auth(app_client),
            json={
                "evidence_id": "ev-api-1",
                "mode": "parse-only",
                "use_fallback": True,
            },
        )

        # Assert
        assert response.status_code == 202
        body = response.json()
        assert "pipeline_id" in body
        assert body["is_complete"] is True
    finally:
        container.services.analysis_service.reset_override()


def test_get_analysis_returns_404_for_unknown_pipeline(app_client: TestClient) -> None:
    """Verify GET /api/v1/analysis/{id} returns 404 when pipeline is missing."""
    # Arrange
    from dfat.core.exceptions import EvidenceNotFoundError

    container = app_client.app.state.container
    service = AsyncMock()
    service.get_analysis_status = AsyncMock(
        side_effect=EvidenceNotFoundError("Pipeline not found")
    )
    container.services.analysis_service.override(service)

    try:
        # Act
        response = app_client.get(
            "/api/v1/analysis/missing-pipeline",
            headers=_auth(app_client),
        )

        # Assert
        assert response.status_code == 404
    finally:
        container.services.analysis_service.reset_override()


def test_get_report_returns_404_for_unknown_report(app_client: TestClient) -> None:
    """Verify GET /api/v1/reports/{id} returns 404 for missing reports."""
    # Arrange
    from dfat.core.exceptions import EvidenceNotFoundError

    container = app_client.app.state.container
    service = AsyncMock()
    service.get_report = AsyncMock(
        side_effect=EvidenceNotFoundError("Report not found")
    )
    container.services.report_service.override(service)

    try:
        # Act
        response = app_client.get(
            "/api/v1/reports/missing-report",
            headers=_auth(app_client),
        )

        # Assert
        assert response.status_code == 404
    finally:
        container.services.report_service.reset_override()


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
    container = app_client.app.state.container
    service = AsyncMock()
    service.get_report = AsyncMock(return_value=report)
    service.get_json_report = AsyncMock(return_value=report.json_report)
    service.get_narrative_report = AsyncMock(return_value=report.narrative_report)
    container.services.report_service.override(service)

    try:
        # Act
        summary = app_client.get("/api/v1/reports/rep-1", headers=_auth(app_client))
        json_resp = app_client.get(
            "/api/v1/reports/rep-1/json",
            headers=_auth(app_client),
        )
        narrative = app_client.get(
            "/api/v1/reports/rep-1/narrative",
            headers=_auth(app_client),
        )

        # Assert
        assert summary.status_code == 200
        assert summary.json()["report_id"] == "rep-1"
        assert json_resp.status_code == 200
        assert json_resp.json()["integrity_hash"] == "d" * 64
        assert narrative.status_code == 200
        assert narrative.text == "Narrative body"
    finally:
        container.services.report_service.reset_override()


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
    evaluation_service = AsyncMock()
    evaluation_service.run_benchmark_for_dataset = AsyncMock(return_value=result)
    evaluation_service.get_benchmark_results = AsyncMock(return_value=[result])
    container = app_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)

    try:
        # Act
        created = app_client.post(
            "/api/v1/evaluation/benchmark",
            headers=_admin_auth(app_client),
            json={
                "evidence_id": "ev-1",
                "ground_truth_dataset": "sample",
                "dataset_source": "dfrws",
            },
        )
        listed = app_client.get(
            "/api/v1/evaluation/benchmark/results",
            headers=_auth(app_client),
        )

        # Assert
        assert created.status_code == 200
        assert created.json()["benchmark_id"] == "bench-1"
        assert listed.status_code == 200
        assert len(listed.json()) == 1
    finally:
        container.services.evaluation_service.reset_override()


def test_report_verify_and_pdf_export(app_client: TestClient, tmp_path: Path) -> None:
    """Verify integrity verification and PDF download endpoints."""
    report = ForensicReport(
        report_id="rep-1",
        case=CaseMetadata(case_id="c1", case_name="Case", investigator="Inv"),
        json_report=JSONReport(
            report_id="json-1",
            evidence_id="ev-1",
            artefact_data=[{"artefact_id": "a1", "category": "event_log", "raw_data": {}}],
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
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 mock")
    from dfat.reporting.integrity import IntegrityVerificationResult

    service = AsyncMock()
    service.get_report = AsyncMock(return_value=report)
    service.verify_integrity = AsyncMock(
        return_value=IntegrityVerificationResult(
            is_valid=True,
            integrity_hash_match=True,
            schema_version_valid=True,
            report_id_valid=True,
            issues=[],
        )
    )
    service.export_pdf = AsyncMock(return_value=pdf_path)
    container = app_client.app.state.container
    container.services.report_service.override(service)

    try:
        verified = app_client.post(
            "/api/v1/reports/rep-1/verify",
            headers=_auth(app_client),
        )
        pdf = app_client.get(
            "/api/v1/reports/rep-1/export/pdf",
            headers=_auth(app_client),
        )
        assert verified.status_code == 200
        assert verified.json()["is_valid"] is True
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")
    finally:
        container.services.report_service.reset_override()


def test_usability_respond_anonymous_and_results_require_auth(
    app_client: TestClient,
) -> None:
    """Verify anonymous usability submit; analysis requires auth."""
    evaluation_service = AsyncMock()
    evaluation_service.collect_usability_response = AsyncMock(
        return_value="11111111-1111-1111-1111-111111111111"
    )
    evaluation_service.get_usability_analysis = AsyncMock(
        return_value={"total_responses": 1, "usefulness_percentage": 100.0}
    )
    evaluation_service.get_questionnaire_instrument = MagicMock(
        return_value={"instrument_version": "1.0.0", "questions": []}
    )
    container = app_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)

    try:
        unauth_results = app_client.get("/api/v1/evaluation/usability/results")
        assert unauth_results.status_code in {401, 403}

        submitted = app_client.post(
            "/api/v1/evaluation/usability/respond",
            json={"ratings": {"usefulness": 5, "accuracy": 4, "clarity": 5}},
        )
        assert submitted.status_code == 201
        assert submitted.json()["participant_id"]

        questionnaire = app_client.get("/api/v1/evaluation/usability/questionnaire")
        assert questionnaire.status_code == 200

        results = app_client.get(
            "/api/v1/evaluation/usability/results",
            headers=_admin_auth(app_client),
        )
        assert results.status_code == 200
        assert results.json()["total_responses"] == 1
    finally:
        container.services.evaluation_service.reset_override()


def test_analysis_rejects_invalid_mode(app_client: TestClient) -> None:
    """Verify AnalysisRunRequest rejects modes outside the allowed pattern."""
    # Arrange / Act
    response = app_client.post(
        "/api/v1/analysis",
        headers=_auth(app_client),
        json={"evidence_id": "ev-1", "mode": "invalid-mode"},
    )

    # Assert
    assert response.status_code == 422
