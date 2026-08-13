"""Forensic report retrieval, export, and integrity services."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from dfat.case_management.enums import CaseStatus
from dfat.core.exceptions import EvidenceNotFoundError
from dfat.core.models.case import Case
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.report_repo import SQLAlchemyReportRepository

if TYPE_CHECKING:
    from dfat.reporting.exporters.html_exporter import HTMLReportExporter
    from dfat.reporting.exporters.json_file_exporter import JSONFileExporter
    from dfat.reporting.exporters.pdf_exporter import PDFReportExporter
    from dfat.reporting.generators.audit_report import AuditReportGenerator, AuditTrailReport
    from dfat.reporting.generators.custody_report import CustodyReport, CustodyReportGenerator
    from dfat.reporting.integrity import IntegrityVerificationResult, ReportIntegrityVerifier
    from dfat.reporting.reproducibility import ReproducibilityResult, ReproducibilityVerifier


class ReportService:
    """Business logic for dual-output report retrieval and export."""

    def __init__(
        self,
        report_repo: SQLAlchemyReportRepository,
        audit_repo: SQLAlchemyAuditRepository,
        pdf_exporter: PDFReportExporter,
        html_exporter: HTMLReportExporter,
        json_file_exporter: JSONFileExporter,
        integrity_verifier: ReportIntegrityVerifier,
        reproducibility_verifier: ReproducibilityVerifier,
        custody_report_generator: CustodyReportGenerator,
        audit_report_generator: AuditReportGenerator,
        case_repo: SQLAlchemyCaseRepository,
        evidence_repo: SQLAlchemyEvidenceRepository,
        export_dir: Optional[Path] = None,
    ) -> None:
        """Initialise the report service."""
        self._report_repo = report_repo
        self._audit_repo = audit_repo
        self._pdf_exporter = pdf_exporter
        self._html_exporter = html_exporter
        self._json_file_exporter = json_file_exporter
        self._integrity_verifier = integrity_verifier
        self._reproducibility_verifier = reproducibility_verifier
        self._custody_report_generator = custody_report_generator
        self._audit_report_generator = audit_report_generator
        self._case_repo = case_repo
        self._evidence_repo = evidence_repo
        self._export_dir = (
            Path(export_dir) if export_dir else Path(tempfile.gettempdir()) / "dfat_exports"
        )
        self._export_dir.mkdir(parents=True, exist_ok=True)

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

    async def export_pdf(self, report_id: str) -> Path:
        """Export a report as PDF (or plaintext fallback) and return the path."""
        report = await self.get_report(report_id)
        return self._pdf_exporter.export(report)

    async def export_html(self, report_id: str) -> Path:
        """Export a report as self-contained HTML and return the path."""
        report = await self.get_report(report_id)
        case = await self._resolve_case(report)
        return self._html_exporter.export(report, case)

    async def export_json_file(self, report_id: str) -> Path:
        """Export the JSON report layer to a verified file."""
        json_report = await self.get_json_report(report_id)
        return self._json_file_exporter.export(json_report, self._export_dir)

    async def verify_integrity(self, report_id: str) -> IntegrityVerificationResult:
        """Verify integrity of the stored JSON report layer."""
        document = await self._json_document(report_id)
        return self._integrity_verifier.verify_report(document)

    async def compare_reports(
        self,
        report_id_a: str,
        report_id_b: str,
    ) -> ReproducibilityResult:
        """Compare two reports for artefact-layer reproducibility."""
        doc_a = await self._json_document(report_id_a)
        doc_b = await self._json_document(report_id_b)
        return self._reproducibility_verifier.compare_reports(doc_a, doc_b)

    async def get_custody_report(self, report_id: str) -> CustodyReport:
        """Generate a custody report for the evidence linked to a forensic report."""
        report = await self.get_report(report_id)
        evidence_id = report.json_report.evidence_id
        case = await self._resolve_case(report)
        evidence = await self._evidence_repo.get(evidence_id)
        file_path = getattr(evidence, "file_path", None) if evidence is not None else None
        return await self._custody_report_generator.generate(
            evidence_id,
            case,
            evidence_file_path=file_path,
        )

    async def get_audit_trail_report(self, report_id: str) -> AuditTrailReport:
        """Generate an audit trail report for the evidence linked to a report."""
        report = await self.get_report(report_id)
        evidence_id = report.json_report.evidence_id
        return await self._audit_report_generator.generate(evidence_id)

    async def _json_document(self, report_id: str) -> dict[str, Any]:
        """Build a verifier-compatible document from a stored JSON report."""
        json_report = await self.get_json_report(report_id)
        return {
            "schema_version": json_report.schema_version,
            "report_id": json_report.report_id,
            "evidence_id": json_report.evidence_id,
            "generated_at": json_report.generated_at.isoformat(),
            "integrity_hash": json_report.integrity_hash,
            "artefacts": list(json_report.artefact_data),
            "artefact_data": list(json_report.artefact_data),
        }

    async def _resolve_case(self, report: ForensicReport) -> Case:
        """Resolve a full ``Case`` for HTML/custody export, with metadata fallback."""
        case_id = report.case.case_id
        stored = await self._case_repo.get(case_id)
        if stored is not None:
            return stored
        return Case(metadata=report.case, status=CaseStatus.CREATED)
