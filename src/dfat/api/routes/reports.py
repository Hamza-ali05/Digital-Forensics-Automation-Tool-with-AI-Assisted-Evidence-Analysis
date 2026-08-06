"""Forensic report retrieval API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from dfat.api.dependencies import get_report_repository
from dfat.api.schemas.responses import ReportResponse
from dfat.core.exceptions import EvidenceNotFoundError
from dfat.core.models.report import ForensicReport
from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository

router = APIRouter(prefix="/reports", tags=["reports"])


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


def _require_report(
    report_id: str,
    report_repo: FileSystemReportRepository,
) -> ForensicReport:
    """Load a report or raise a not-found error."""
    report = report_repo.get(report_id)
    if report is None:
        raise EvidenceNotFoundError(
            f"Report not found: {report_id}",
            context={"report_id": report_id},
        )
    return report


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: str,
    report_repo: FileSystemReportRepository = Depends(get_report_repository),
) -> ReportResponse:
    """Get full forensic report summary metadata."""
    return _to_report_response(_require_report(report_id, report_repo))


@router.get("/{report_id}/json")
def get_report_json(
    report_id: str,
    report_repo: FileSystemReportRepository = Depends(get_report_repository),
) -> dict:
    """Get the JSON report component only."""
    report = _require_report(report_id, report_repo)
    return report.json_report.model_dump(mode="json")


@router.get("/{report_id}/narrative", response_class=PlainTextResponse)
def get_report_narrative(
    report_id: str,
    report_repo: FileSystemReportRepository = Depends(get_report_repository),
) -> str:
    """Get the narrative report component only."""
    report = _require_report(report_id, report_repo)
    return report.narrative_report.summary_text
