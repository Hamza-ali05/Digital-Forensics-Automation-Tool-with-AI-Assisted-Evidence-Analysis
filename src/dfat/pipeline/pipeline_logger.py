"""Structured logging for pipeline execution events (app logger + audit)."""

from __future__ import annotations

from typing import Any

from dfat.core.enums import PipelineStage
from dfat.pipeline.models import PipelineJob
from dfat.services.audit_service import AuditService


class PipelineLogger:
    """Structured logging specifically for pipeline execution events.

    Every method writes to the structured application logger and the
    dual-write ``AuditService`` trail.
    """

    def __init__(self, audit_service: AuditService, app_logger: Any) -> None:
        """Initialise the pipeline logger.

        Args:
            audit_service: Dual-write forensic audit trail service.
            app_logger: Structlog (or compatible) bound logger.
        """
        self._audit = audit_service
        self._log = app_logger

    async def log_job_start(self, job: PipelineJob) -> None:
        """Log that a pipeline job has started executing."""
        self._log.info(
            "pipeline.job_start",
            job_id=job.job_id,
            evidence_id=job.evidence_id,
            case_id=job.case_id,
            user_id=job.user_id,
            mode=job.mode,
        )
        await self._audit.log_action(
            stage=PipelineStage.ACQUISITION,
            action="PIPELINE_JOB_STARTED",
            evidence_id=job.evidence_id,
            user_id=job.user_id,
            details={
                "job_id": job.job_id,
                "case_id": job.case_id,
                "mode": job.mode,
            },
        )

    async def log_stage_start(self, job_id: str, stage: PipelineStage) -> None:
        """Log that a pipeline stage has started."""
        self._log.info(
            "pipeline.stage_start",
            job_id=job_id,
            stage=stage.value,
        )
        await self._audit.log_action(
            stage=stage,
            action="PIPELINE_STAGE_STARTED",
            details={"job_id": job_id, "stage": stage.value},
        )

    async def log_stage_complete(
        self,
        job_id: str,
        stage: PipelineStage,
        duration: float,
        artefacts: int,
    ) -> None:
        """Log successful stage completion with duration and artefact count."""
        self._log.info(
            "pipeline.stage_complete",
            job_id=job_id,
            stage=stage.value,
            duration_seconds=duration,
            artefacts=artefacts,
        )
        await self._audit.log_action(
            stage=stage,
            action="PIPELINE_STAGE_COMPLETED",
            details={
                "job_id": job_id,
                "duration_seconds": duration,
                "artefacts": artefacts,
            },
        )

    async def log_parser_start(self, job_id: str, parser_name: str) -> None:
        """Log that an artefact parser has started."""
        self._log.info(
            "pipeline.parser_start",
            job_id=job_id,
            parser_name=parser_name,
        )
        await self._audit.log_action(
            stage=PipelineStage.PARSING,
            action="PIPELINE_PARSER_STARTED",
            details={"job_id": job_id, "parser_name": parser_name},
        )

    async def log_parser_complete(
        self,
        job_id: str,
        parser_name: str,
        duration: float,
        artefacts: int,
    ) -> None:
        """Log successful parser completion with duration and artefact count."""
        self._log.info(
            "pipeline.parser_complete",
            job_id=job_id,
            parser_name=parser_name,
            duration_seconds=duration,
            artefacts=artefacts,
        )
        await self._audit.log_action(
            stage=PipelineStage.PARSING,
            action="PIPELINE_PARSER_COMPLETED",
            details={
                "job_id": job_id,
                "parser_name": parser_name,
                "duration_seconds": duration,
                "artefacts": artefacts,
            },
        )

    async def log_parser_error(
        self,
        job_id: str,
        parser_name: str,
        error: str,
    ) -> None:
        """Log a parser failure."""
        self._log.error(
            "pipeline.parser_error",
            job_id=job_id,
            parser_name=parser_name,
            error=error,
        )
        await self._audit.log_action(
            stage=PipelineStage.PARSING,
            action="PIPELINE_PARSER_FAILED",
            details={
                "job_id": job_id,
                "parser_name": parser_name,
                "error": error,
            },
        )

    async def log_job_complete(self, job: PipelineJob) -> None:
        """Log that a pipeline job completed successfully."""
        self._log.info(
            "pipeline.job_complete",
            job_id=job.job_id,
            evidence_id=job.evidence_id,
            total_duration_seconds=job.total_duration_seconds,
            artefact_count=job.artefact_count,
        )
        await self._audit.log_action(
            stage=job.current_stage or PipelineStage.EVALUATION,
            action="PIPELINE_JOB_COMPLETED",
            evidence_id=job.evidence_id,
            user_id=job.user_id,
            details={
                "job_id": job.job_id,
                "total_duration_seconds": job.total_duration_seconds,
                "artefact_count": job.artefact_count,
            },
        )

    async def log_job_failed(self, job: PipelineJob, error: str) -> None:
        """Log that a pipeline job failed."""
        self._log.error(
            "pipeline.job_failed",
            job_id=job.job_id,
            evidence_id=job.evidence_id,
            error=error,
        )
        await self._audit.log_action(
            stage=job.current_stage or PipelineStage.ACQUISITION,
            action="PIPELINE_JOB_FAILED",
            evidence_id=job.evidence_id,
            user_id=job.user_id,
            details={"job_id": job.job_id, "error": error},
        )
