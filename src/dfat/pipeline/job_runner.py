"""Execute pipeline jobs by sequencing registered stage handlers."""

from __future__ import annotations

from datetime import UTC, datetime

from dfat.core.enums import PipelineStage
from dfat.core.models.pipeline import StageResult
from dfat.pipeline.enums import JobStatus, StageStatus
from dfat.pipeline.job_manager import JobManager
from dfat.pipeline.models import PipelineJob, StageExecution
from dfat.pipeline.stage_interface import PipelineContext
from dfat.pipeline.stage_registry import StageRegistry
from dfat.services.audit_service import AuditService
from dfat.shared.timing import PerformanceTimer


class JobRunner:
    """Run a ``PipelineJob`` through ordered ``IPipelineStage`` handlers."""

    def __init__(
        self,
        job_manager: JobManager,
        stage_registry: StageRegistry,
        audit_service: AuditService,
    ) -> None:
        """Initialise the job runner.

        Args:
            job_manager: In-memory job queue/status manager.
            stage_registry: Registry of executable pipeline stages.
            audit_service: Dual-write audit trail service.
        """
        self._job_manager = job_manager
        self._registry = stage_registry
        self._audit_service = audit_service

    async def run_job(
        self,
        job: PipelineJob,
        context: PipelineContext,
    ) -> PipelineJob:
        """Execute all ordered stages for ``job`` and return the updated job.

        Args:
            job: Pipeline job to execute (must already exist in the manager).
            context: Mutable stage context carrying accumulated outputs.

        Returns:
            Updated ``PipelineJob`` (``COMPLETED`` or ``FAILED`` / ``CANCELLED``).
        """
        await self._job_manager.update_job_status(job.job_id, JobStatus.RUNNING)
        job = await self._refresh(job.job_id)
        context.job = job

        await self._audit_service.log_action(
            stage=PipelineStage.ACQUISITION,
            action="PIPELINE_JOB_STARTED",
            evidence_id=job.evidence_id,
            user_id=job.user_id,
            details={"job_id": job.job_id, "mode": job.mode},
        )

        try:
            stages = self._registry.get_ordered_stages(job.mode)
        except (KeyError, ValueError) as exc:
            await self._job_manager.update_job_status(
                job.job_id,
                JobStatus.FAILED,
                error=str(exc),
            )
            return await self._refresh(job.job_id)

        for stage_handler in stages:
            job = await self._refresh(job.job_id)
            if job.status is JobStatus.CANCELLED:
                return job

            stage = stage_handler.stage_name
            execution = StageExecution(
                stage=stage,
                status=StageStatus.RUNNING,
                started_at=datetime.now(UTC),
            )
            await self._job_manager.update_stage(job.job_id, stage, execution)
            await self._job_manager.update_job_status(job.job_id, JobStatus.RUNNING)
            context.job = await self._refresh(job.job_id)

            try:
                preconditions_ok = await stage_handler.validate_preconditions(context)
            except Exception as exc:  # noqa: BLE001 — stage isolation
                await self._fail_stage(
                    job.job_id,
                    stage,
                    execution,
                    errors=[f"precondition error: {exc}"],
                )
                return await self._refresh(job.job_id)

            if not preconditions_ok:
                await self._fail_stage(
                    job.job_id,
                    stage,
                    execution,
                    errors=["Stage preconditions not satisfied"],
                )
                return await self._refresh(job.job_id)

            with PerformanceTimer() as timer:
                try:
                    result: StageResult = await stage_handler.execute(context)
                except Exception as exc:  # noqa: BLE001 — stage isolation
                    execution.duration_seconds = timer.elapsed_seconds
                    context.stage_timings[stage.value] = timer.elapsed_seconds
                    await self._fail_stage(
                        job.job_id,
                        stage,
                        execution,
                        errors=[str(exc)],
                    )
                    return await self._refresh(job.job_id)

            execution.duration_seconds = (
                result.duration_seconds
                if result.duration_seconds
                else timer.elapsed_seconds
            )
            context.stage_timings[stage.value] = execution.duration_seconds
            execution.completed_at = datetime.now(UTC)
            execution.output_summary = (
                dict(result.output_data)
                if isinstance(result.output_data, dict)
                else {"output": result.output_data}
            )
            execution.errors = list(result.errors)

            if not result.success:
                await self._fail_stage(
                    job.job_id,
                    stage,
                    execution,
                    errors=execution.errors or ["Stage reported failure"],
                )
                return await self._refresh(job.job_id)

            execution.status = StageStatus.COMPLETED
            await self._job_manager.update_stage(job.job_id, stage, execution)
            await self._audit_service.log_action(
                stage=stage,
                action="PIPELINE_STAGE_COMPLETED",
                evidence_id=job.evidence_id,
                user_id=job.user_id,
                details={
                    "job_id": job.job_id,
                    "duration_seconds": execution.duration_seconds,
                },
            )

        job = await self._refresh(job.job_id)
        if job.status is JobStatus.CANCELLED:
            return job

        await self._job_manager.update_job_status(job.job_id, JobStatus.COMPLETED)
        completed = await self._refresh(job.job_id)
        await self._audit_service.log_action(
            stage=completed.current_stage or PipelineStage.EVALUATION,
            action="PIPELINE_JOB_COMPLETED",
            evidence_id=completed.evidence_id,
            user_id=completed.user_id,
            details={
                "job_id": completed.job_id,
                "total_duration_seconds": completed.total_duration_seconds,
                "artefact_count": completed.artefact_count,
            },
        )
        return completed

    async def _fail_stage(
        self,
        job_id: str,
        stage: PipelineStage,
        execution: StageExecution,
        *,
        errors: list[str],
    ) -> None:
        """Mark a stage and job as failed and audit the failure."""
        execution.status = StageStatus.FAILED
        execution.completed_at = datetime.now(UTC)
        execution.errors = list(errors)
        await self._job_manager.update_stage(job_id, stage, execution)
        error_message = "; ".join(errors)
        await self._job_manager.update_job_status(
            job_id,
            JobStatus.FAILED,
            error=error_message,
        )
        job = await self._refresh(job_id)
        await self._audit_service.log_action(
            stage=stage,
            action="PIPELINE_JOB_FAILED",
            evidence_id=job.evidence_id,
            user_id=job.user_id,
            details={"job_id": job_id, "errors": errors},
        )

    async def _refresh(self, job_id: str) -> PipelineJob:
        """Reload the job from the manager (always present after submit)."""
        job = await self._job_manager.get_job(job_id)
        assert job is not None
        return job
