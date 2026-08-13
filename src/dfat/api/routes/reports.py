"""Forensic report retrieval, export, verify, custody, and audit API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, PlainTextResponse

from dfat.api.dependencies import get_report_service, require_permission
from dfat.api.schemas.requests import ReportCompareRequest
from dfat.api.schemas.responses import (
    IntegrityVerifyResponse,
    ReportResponse,
    ReproducibilityCompareResponse,
)
from dfat.core.models.report import ForensicReport
from dfat.database.models.user import UserORM
from dfat.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


def _to_report_response(report: ForensicReport) -> ReportResponse:
    """Map a ForensicReport to the summary API response."""
    return ReportResponse(
        report_id=report.report_id,
        case_name=report.case.case_name,
        json_report_url=f"/api/v1/reports/{report.report_id}/json",
        narrative_report_url=f"/api/v1/reports/{report.report_id}/narrative",
        generated_at=report.json_report.generated_at,
        pipeline_duration_seconds=report.pipeline_duration_seconds,
    )


def _media_type_for(path: Path) -> str:
    """Infer a download media type from the export path suffix."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".html":
        return "text/html"
    if suffix == ".json":
        return "application/json"
    return "text/plain"


@router.post("/compare", response_model=ReproducibilityCompareResponse)
async def compare_reports(
    body: ReportCompareRequest,
    _: UserORM = Depends(require_permission("reports", "read")),
    report_service: ReportService = Depends(get_report_service),
) -> ReproducibilityCompareResponse:
    """Compare two reports for artefact-layer reproducibility."""
    result = await report_service.compare_reports(body.report_id_a, body.report_id_b)
    return ReproducibilityCompareResponse.model_validate(result.model_dump())


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    _: UserORM = Depends(require_permission("reports", "read")),
    report_service: ReportService = Depends(get_report_service),
) -> ReportResponse:
    """Get full forensic report summary metadata."""
    report = await report_service.get_report(report_id)
    return _to_report_response(report)


@router.get("/{report_id}/json")
async def get_report_json(
    report_id: str,
    _: UserORM = Depends(require_permission("reports", "read")),
    report_service: ReportService = Depends(get_report_service),
) -> dict:
    """Get the JSON report component only."""
    json_report = await report_service.get_json_report(report_id)
    return json_report.model_dump(mode="json")


@router.get("/{report_id}/narrative", response_class=PlainTextResponse)
async def get_report_narrative(
    report_id: str,
    _: UserORM = Depends(require_permission("reports", "read")),
    report_service: ReportService = Depends(get_report_service),
) -> str:
    """Get the narrative report component only."""
    narrative = await report_service.get_narrative_report(report_id)
    return narrative.summary_text


@router.get("/{report_id}/export/pdf")
async def export_report_pdf(
    report_id: str,
    _: UserORM = Depends(require_permission("reports", "read")),
    report_service: ReportService = Depends(get_report_service),
) -> FileResponse:
    """Download the PDF (or plaintext fallback) export of a report."""
    path = await report_service.export_pdf(report_id)
    return FileResponse(
        path=path,
        filename=path.name,
        media_type=_media_type_for(path),
    )


@router.get("/{report_id}/export/html")
async def export_report_html(
    report_id: str,
    _: UserORM = Depends(require_permission("reports", "read")),
    report_service: ReportService = Depends(get_report_service),
) -> FileResponse:
    """Download the HTML export of a report."""
    path = await report_service.export_html(report_id)
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="text/html",
    )


@router.get("/{report_id}/export/json-file")
async def export_report_json_file(
    report_id: str,
    _: UserORM = Depends(require_permission("reports", "read")),
    report_service: ReportService = Depends(get_report_service),
) -> FileResponse:
    """Download the verified JSON file export of a report."""
    path = await report_service.export_json_file(report_id)
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/json",
    )


@router.post("/{report_id}/verify", response_model=IntegrityVerifyResponse)
async def verify_report_integrity(
    report_id: str,
    _: UserORM = Depends(require_permission("reports", "read")),
    report_service: ReportService = Depends(get_report_service),
) -> IntegrityVerifyResponse:
    """Verify integrity of the structured JSON report layer."""
    result = await report_service.verify_integrity(report_id)
    return IntegrityVerifyResponse.model_validate(result.model_dump())


@router.get("/{report_id}/custody")
async def get_report_custody(
    report_id: str,
    _: UserORM = Depends(require_permission("reports", "read")),
    report_service: ReportService = Depends(get_report_service),
) -> dict:
    """Get the chain-of-custody report for the report's evidence."""
    custody = await report_service.get_custody_report(report_id)
    return custody.model_dump(mode="json")


@router.get("/{report_id}/audit-trail")
async def get_report_audit_trail(
    report_id: str,
    _: UserORM = Depends(require_permission("reports", "read")),
    report_service: ReportService = Depends(get_report_service),
) -> dict:
    """Get the audit trail report for the report's evidence."""
    audit = await report_service.get_audit_trail_report(report_id)
    return audit.model_dump(mode="json")
