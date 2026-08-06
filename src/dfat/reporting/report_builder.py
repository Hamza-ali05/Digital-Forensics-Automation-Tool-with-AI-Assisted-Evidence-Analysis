"""Dual-output report builder combining JSON and narrative layers."""

from __future__ import annotations

from typing import Any, Optional

from dfat.core.enums import PipelineStage
from dfat.core.interfaces.reporter import IReportGenerator
from dfat.core.interfaces.repository import IReportRepository
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler


class DualOutputReportBuilder(IReportGenerator):
    """Build, persist, and audit dual-output forensic reports."""

    def __init__(
        self,
        json_exporter: StructuredJSONExporter,
        narrative_assembler: NarrativeAssembler,
        report_repo: IReportRepository,
        audit_logger: ForensicAuditLogger,
    ) -> None:
        """Initialise the dual-output report builder.

        Args:
            json_exporter: Structured JSON exporter.
            narrative_assembler: Narrative assembler.
            report_repo: Report persistence repository.
            audit_logger: Forensic audit logger.
        """
        self._json_exporter = json_exporter
        self._narrative_assembler = narrative_assembler
        self._report_repo = report_repo
        self._audit_logger = audit_logger
        self._context_case: Optional[CaseMetadata] = None
        self._context_timings: dict[str, float] = {}
        self._context_ranked: list[RankedArtefact] = []
        self._context_evidence_id: Optional[str] = None

    def generate_json_report(
        self,
        artefact_set: ArtefactSet,
        ranked: list[RankedArtefact],
    ) -> JSONReport:
        """Generate the machine-readable JSON report layer.

        Args:
            artefact_set: Parsed artefact collection.
            ranked: Triaged ranked artefacts.

        Returns:
            Structured JSON report.
        """
        case = self._context_case or CaseMetadata(
            case_name="Unspecified",
            investigator="system",
        )
        timings = dict(self._context_timings)
        return self._json_exporter.export(
            artefact_set=artefact_set,
            ranked_artefacts=ranked,
            case=case,
            stage_timings=timings,
        )

    def generate_narrative_report(
        self,
        summary: str,
        llm_model: str,
        params: dict[str, Any],
    ) -> NarrativeReport:
        """Generate the human-readable narrative report.

        Args:
            summary: Investigative summary text.
            llm_model: Local model identifier used for generation.
            params: Generation parameter snapshot.

        Returns:
            Narrative report artefact.
        """
        case_name = (
            self._context_case.case_name if self._context_case is not None else "Unknown Case"
        )
        evidence_id = self._context_evidence_id or "unknown"
        return self._narrative_assembler.assemble(
            summary_text=summary,
            llm_model=llm_model,
            generation_params=params,
            ranked_artefacts=list(self._context_ranked),
            evidence_id=evidence_id,
            case_name=case_name,
        )

    def generate_full_report(
        self,
        case: CaseMetadata,
        json_report: JSONReport,
        narrative: NarrativeReport,
        duration: float,
        timings: dict[str, float],
    ) -> ForensicReport:
        """Combine JSON and narrative outputs into a full forensic report.

        Args:
            case: Case metadata associated with the report.
            json_report: Machine-readable report component.
            narrative: Human-readable report component.
            duration: End-to-end pipeline duration in seconds.
            timings: Per-stage timing map in seconds.

        Returns:
            Combined dual-output forensic report.
        """
        report = ForensicReport(
            case=case,
            json_report=json_report,
            narrative_report=narrative,
            pipeline_duration_seconds=duration,
            stage_timings=dict(timings),
        )
        self._report_repo.save(report)
        self._audit_logger.log_action(
            stage=PipelineStage.REPORTING,
            action="REPORT_GENERATED",
            evidence_id=json_report.evidence_id,
            details={
                "report_id": report.report_id,
                "json_report_id": json_report.report_id,
                "narrative_report_id": narrative.report_id,
                "integrity_hash": json_report.integrity_hash,
                "duration_seconds": duration,
            },
        )
        return report

    def build_complete_report(
        self,
        case: CaseMetadata,
        artefact_set: ArtefactSet,
        ranked_artefacts: list[RankedArtefact],
        summary_text: str,
        llm_model: str,
        generation_params: dict[str, Any],
        stage_timings: dict[str, float],
    ) -> ForensicReport:
        """Build JSON + narrative reports and return the combined result.

        This is the primary API for the pipeline orchestrator.

        Args:
            case: Case metadata.
            artefact_set: Parsed artefact set.
            ranked_artefacts: Triaged ranked artefacts.
            summary_text: Narrative summary body.
            llm_model: Model identifier.
            generation_params: Generation parameter snapshot.
            stage_timings: Pipeline stage timings.

        Returns:
            Persisted ``ForensicReport``.
        """
        self._context_case = case
        self._context_timings = dict(stage_timings)
        self._context_ranked = list(ranked_artefacts)
        self._context_evidence_id = artefact_set.evidence_id

        json_report = self.generate_json_report(artefact_set, ranked_artefacts)
        narrative = self.generate_narrative_report(
            summary_text,
            llm_model,
            generation_params,
        )
        duration = float(sum(stage_timings.values()))
        return self.generate_full_report(
            case=case,
            json_report=json_report,
            narrative=narrative,
            duration=duration,
            timings=stage_timings,
        )
