"""Reports endpoint API contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.evidence_management.models import HashSet
from dfat.reporting.generators.custody_report import CustodyReport
from dfat.reporting.integrity import IntegrityVerificationResult
from dfat.reporting.reproducibility import ReproducibilityResult
from tests.contract.conftest import AuthedClient


def _sample_report(report_id: str = "rep-contract-1") -> ForensicReport:
    return ForensicReport(
        report_id=report_id,
        case=CaseMetadata(case_id="c1", case_name="Case", investigator="Inv"),
        json_report=JSONReport(
            report_id=f"json-{report_id}",
            evidence_id="ev-1",
            artefact_data=[
                {"artefact_id": "a1", "category": "event_log", "raw_data": {}}
            ],
            integrity_hash="d" * 64,
            schema_version="1.0.0",
        ),
        narrative_report=NarrativeReport(
            report_id=f"narr-{report_id}",
            evidence_id="ev-1",
            summary_text="Narrative body",
            llm_model_used="Mock",
            generation_parameters={},
        ),
        pipeline_duration_seconds=1.5,
        stage_timings={},
    )


def test_get_report_returns_full_forensic_report(
    analyst_client: AuthedClient,
) -> None:
    report = _sample_report()
    service = AsyncMock()
    service.get_report = AsyncMock(return_value=report)
    container = analyst_client.client.app.state.container
    container.services.report_service.override(service)
    try:
        response = analyst_client.get("/api/v1/reports/rep-contract-1")
        assert response.status_code == 200
        body = response.json()
        assert body["report_id"] == "rep-contract-1"
        assert "json_report_url" in body or "case_name" in body
    finally:
        container.services.report_service.reset_override()


def test_get_json_report_returns_schema_valid_json(
    analyst_client: AuthedClient,
) -> None:
    report = _sample_report()
    service = AsyncMock()
    service.get_json_report = AsyncMock(return_value=report.json_report)
    container = analyst_client.client.app.state.container
    container.services.report_service.override(service)
    try:
        response = analyst_client.get("/api/v1/reports/rep-contract-1/json")
        assert response.status_code == 200
        body = response.json()
        assert body["integrity_hash"] == "d" * 64
        assert "artefact_data" in body or "artefacts" in body
    finally:
        container.services.report_service.reset_override()


def test_export_pdf_returns_file_download(
    analyst_client: AuthedClient,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 mock")
    service = AsyncMock()
    service.export_pdf = AsyncMock(return_value=pdf_path)
    container = analyst_client.client.app.state.container
    container.services.report_service.override(service)
    try:
        response = analyst_client.get("/api/v1/reports/rep-contract-1/export/pdf")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")
    finally:
        container.services.report_service.reset_override()


def test_verify_report_integrity(analyst_client: AuthedClient) -> None:
    service = AsyncMock()
    service.verify_integrity = AsyncMock(
        return_value=IntegrityVerificationResult(
            is_valid=True,
            integrity_hash_match=True,
            schema_version_valid=True,
            report_id_valid=True,
            issues=[],
        )
    )
    container = analyst_client.client.app.state.container
    container.services.report_service.override(service)
    try:
        response = analyst_client.post("/api/v1/reports/rep-contract-1/verify")
        assert response.status_code == 200
        assert response.json()["is_valid"] is True
    finally:
        container.services.report_service.reset_override()


def test_compare_reports_returns_reproducibility(
    analyst_client: AuthedClient,
) -> None:
    service = AsyncMock()
    service.compare_reports = AsyncMock(
        return_value=ReproducibilityResult(
            is_reproducible=True,
            hash_a="a" * 64,
            hash_b="a" * 64,
            hashes_match=True,
            artefact_count_match=True,
            category_distribution_match=True,
            suspicion_distribution_match=True,
            differences=[],
        )
    )
    container = analyst_client.client.app.state.container
    container.services.report_service.override(service)
    try:
        response = analyst_client.post(
            "/api/v1/reports/compare",
            json={"report_id_a": "rep-a", "report_id_b": "rep-b"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "is_reproducible" in body
        assert body["hashes_match"] is True
    finally:
        container.services.report_service.reset_override()


def test_get_custody_report_returns_chain(analyst_client: AuthedClient) -> None:
    now = datetime.now(UTC)
    custody = CustodyReport(
        evidence_id="ev-1",
        case_name="Case",
        evidence_file_path="/tmp/ev.dd",
        hash_set=HashSet(
            md5="0" * 32,
            sha1="1" * 40,
            sha256="a" * 64,
            computed_at=now,
            file_size_bytes=10,
        ),
        chain=[],
        chain_length=0,
        verification={},
        first_acquired=now,
        last_action=now,
        integrity_verified=True,
        generated_at=now,
    )
    service = AsyncMock()
    service.get_custody_report = AsyncMock(return_value=custody)
    container = analyst_client.client.app.state.container
    container.services.report_service.override(service)
    try:
        response = analyst_client.get("/api/v1/reports/rep-contract-1/custody")
        assert response.status_code == 200
        body = response.json()
        assert body["evidence_id"] == "ev-1"
        assert "chain" in body or "chain_length" in body
    finally:
        container.services.report_service.reset_override()
