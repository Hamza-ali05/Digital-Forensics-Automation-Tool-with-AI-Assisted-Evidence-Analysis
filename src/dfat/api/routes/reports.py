"""Forensic report retrieval API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from dfat.api.dependencies import get_report_service, require_permission
from dfat.api.schemas.responses import ReportResponse
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
