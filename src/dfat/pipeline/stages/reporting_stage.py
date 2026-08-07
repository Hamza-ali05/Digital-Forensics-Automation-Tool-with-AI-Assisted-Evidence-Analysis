"""Stage 4 — generate dual-output forensic reports."""

from __future__ import annotations

import logging
import time
from typing import Any

from dfat.core.enums import PipelineStage
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.pipeline import StageResult
from dfat.pipeline.progress_tracker import ProgressNotFoundError, ProgressTracker
from dfat.pipeline.stage_interface import IPipelineStage, PipelineContext
from dfat.reporting.report_builder import DualOutputReportBuilder
from dfat.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class ReportingStage(IPipelineStage):
    """Build and persist a dual-output ``ForensicReport`` from triage outputs."""

    def __init__(
        self,
        report_builder: DualOutputReportBuilder,
        progress_tracker: ProgressTracker,
        audit_service: AuditService,
    ) -> None:
        """Initialise the reporting stage.

        Args:
            report_builder: Dual JSON + narrative report builder.
            progress_tracker: Job/stage progress tracker.
            audit_service: Dual-write audit trail service.
        """
        self._report_builder = report_builder
        self._progress = progress_tracker
        self._audit = audit_service

    @property
    def stage_name(self) -> PipelineStage:
        """Return ``PipelineStage.REPORTING``."""
        return PipelineStage.REPORTING

    @property
    def description(self) -> str:
        """Return a human-readable description of this stage."""
        return "Generate dual-output forensic JSON and narrative reports"

    async def validate_preconditions(self, context: PipelineContext) -> bool:
        """Require artefact set, ranked artefacts, and summary text."""
        return (
            context.artefact_set is not None
            and context.ranked_artefacts is not None
            and context.summary_text is not None
        )

    async def execute(self, context: PipelineContext) -> StageResult:
        """Generate a forensic report and store it on ``context.report``.

        Args:
            context: Shared pipeline context with triage outputs.

        Returns:
            ``StageResult`` for the reporting stage.
        """
        started = time.perf_counter()
        errors: list[str] = []
        job = context.job
        evidence_id = (
            context.evidence.evidence_id
            if context.evidence is not None
            else (context.artefact_set.evidence_id if context.artefact_set else job.evidence_id)
        )

        if (
            context.artefact_set is None
            or context.ranked_artefacts is None
            or context.summary_text is None
        ):
            return StageResult(
                stage=self.stage_name,
                success=False,
                duration_seconds=time.perf_counter() - started,
                errors=[
                    "Reporting requires artefact_set, ranked_artefacts, and summary_text"
                ],
            )

        self._ensure_progress_job(job.job_id)
        self._progress.start_stage(job.job_id, self.stage_name, parser_count=0)

        await self._audit.log_action(
            stage=self.stage_name,
            action="REPORTING_STAGE_STARTED",
            evidence_id=evidence_id,
            user_id=job.user_id,
            details={"job_id": job.job_id},
        )

        try:
            case = self._resolve_case(context)
            llm_model = str(
                context.metadata.get("triage_source")
                or context.metadata.get("llm_model")
                or "dfat-triage"
            )
            generation_params: dict[str, Any] = {
                "use_fallback_analyzer": job.use_fallback_analyzer,
                "triage_source": context.metadata.get("triage_source"),
                "job_mode": job.mode,
            }
            timings = dict(context.stage_timings)

            report = self._report_builder.build_complete_report(
                case=case,
                artefact_set=context.artefact_set,
                ranked_artefacts=list(context.ranked_artefacts),
                summary_text=context.summary_text,
                llm_model=llm_model,
                generation_params=generation_params,
                stage_timings=timings,
            )

            duration = time.perf_counter() - started
            timings[self.stage_name.value] = duration
            report.stage_timings = dict(timings)
            report.pipeline_duration_seconds = float(sum(timings.values()))

            context.report = report
            context.stage_timings[self.stage_name.value] = duration
            context.job.report_id = report.report_id
            context.metadata["report_id"] = report.report_id

            self._progress.complete_stage(job.job_id, self.stage_name, artefacts_found=0)

            await self._audit.log_action(
                stage=self.stage_name,
                action="REPORTING_STAGE_COMPLETED",
                evidence_id=evidence_id,
                user_id=job.user_id,
                details={
                    "job_id": job.job_id,
                    "report_id": report.report_id,
                    "ranked_count": len(context.ranked_artefacts),
                },
            )

            return StageResult(
                stage=self.stage_name,
                success=True,
                duration_seconds=duration,
                output_data={
                    "report_id": report.report_id,
                    "json_report_id": report.json_report.report_id,
                    "narrative_report_id": report.narrative_report.report_id,
                },
                errors=errors,
            )
        except Exception as exc:  # noqa: BLE001 — stage-level failure
            duration = time.perf_counter() - started
            errors.append(str(exc))
            logger.exception("Reporting stage failed for job %s", job.job_id)
            await self._audit.log_action(
                stage=self.stage_name,
                action="REPORTING_STAGE_FAILED",
                evidence_id=evidence_id,
                user_id=job.user_id,
                details={"job_id": job.job_id, "error": str(exc)},
            )
            return StageResult(
                stage=self.stage_name,
                success=False,
                duration_seconds=duration,
                output_data=None,
                errors=errors,
            )

    @staticmethod
    def _resolve_case(context: PipelineContext) -> CaseMetadata:
        """Resolve case metadata from evidence or context metadata."""
        if context.evidence is not None and context.evidence.case is not None:
            return context.evidence.case
        raw = context.metadata.get("case")
        if isinstance(raw, CaseMetadata):
            return raw
        if isinstance(raw, dict):
            return CaseMetadata.model_validate(raw)
        return CaseMetadata(
            case_name=str(context.metadata.get("case_name") or context.job.case_id),
            investigator=str(context.metadata.get("investigator") or context.job.user_id),
        )

    def _ensure_progress_job(self, job_id: str) -> None:
        """Ensure progress tracking has been initialised for ``job_id``."""
        try:
            self._progress.get_progress(job_id)
        except ProgressNotFoundError:
            self._progress.start_job(job_id, total_stages=5)
