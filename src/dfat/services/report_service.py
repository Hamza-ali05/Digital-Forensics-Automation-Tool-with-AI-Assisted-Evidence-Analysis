"""Forensic report retrieval services."""

from __future__ import annotations

from dfat.core.exceptions import EvidenceNotFoundError
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.report_repo import SQLAlchemyReportRepository


class ReportService:
    """Business logic for dual-output report retrieval."""

    def __init__(
        self,
        report_repo: SQLAlchemyReportRepository,
        audit_repo: SQLAlchemyAuditRepository,
    ) -> None:
        """Initialise the report service.

        Args:
            report_repo: Report repository.
            audit_repo: Database audit repository (reserved for future access logging).
        """
        self._report_repo = report_repo
        self._audit_repo = audit_repo

    async def get_report(self, report_id: str) -> ForensicReport:
        """Load a full forensic report by ID."""
        report = await self._report_repo.get(report_id)
        if report is None:
            raise EvidenceNotFoundError(
                f"Report not found: {report_id}",
                context={"report_id": report_id},
            )
        return report

    async def get_json_report(self, report_id: str) -> JSONReport:
        """Return only the JSON report component."""
        report = await self.get_report(report_id)
        return report.json_report

    async def get_narrative_report(self, report_id: str) -> NarrativeReport:
        """Return only the narrative report component."""
        report = await self.get_report(report_id)
        return report.narrative_report

    async def list_reports(self) -> list[ForensicReport]:
        """List all forensic reports."""
        return await self._report_repo.list_all()

    async def get_reports_by_case(self, case_id: str) -> list[ForensicReport]:
        """List reports associated with a case ID."""
        return await self._report_repo.get_by_case(case_id)
