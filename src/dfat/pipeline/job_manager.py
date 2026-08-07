"""In-memory pipeline job queue with status tracking and cancellation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional

from dfat.core.enums import PipelineStage
from dfat.core.exceptions import DFATError
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.models import PipelineJob, StageExecution
from dfat.services.audit_service import AuditService

_TERMINAL_STATUSES = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.TIMED_OUT,
    }
)

_ACTIVE_STATUSES = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.INITIALISING,
        JobStatus.RUNNING,
        JobStatus.STAGE_COMPLETE,
    }
)

_CANCELLABLE_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.RUNNING})


class JobNotFoundError(DFATError):
    """Raised when a pipeline job ID cannot be resolved."""


class JobCancellationError(DFATError):
    """Raised when a job cannot be cancelled in its current status."""


class JobManager:
    """In-memory job queue for forensic pipeline execution."""

    def __init__(
        self,
        audit_service: AuditService,
        max_concurrent: int = 1,
    ) -> None:
        """Initialise the job manager.

        Args:
            audit_service: Dual-write audit trail service.
            max_concurrent: Maximum concurrently running jobs (advisory).
        """
        self._audit_service = audit_service
        self._max_concurrent = max(1, max_concurrent)
        self._jobs: dict[str, PipelineJob] = {}

    @property
    def max_concurrent(self) -> int:
        """Return the configured concurrent-job limit."""
        return self._max_concurrent

    async def submit_job(
        self,
        evidence_id: str,
        case_id: str,
        user_id: str,
        mode: str = "full",
        use_fallback: bool = False,
    ) -> PipelineJob:
        """Create a QUEUED pipeline job and enqueue it.

        Args:
            evidence_id: Target evidence identifier.
            case_id: Owning case identifier.
            user_id: Submitting user identifier.
            mode: Pipeline mode (``full``, ``parse-only``, ``triage-only``).
            use_fallback: Force rule-based triage analyzer.

        Returns:
            Newly created ``PipelineJob`` in ``QUEUED`` status.
        """
        job = PipelineJob(
            evidence_id=evidence_id,
            case_id=case_id,
            user_id=user_id,
            status=JobStatus.QUEUED,
            mode=mode,
            use_fallback_analyzer=use_fallback,
        )
        self._jobs[job.job_id] = job
        await self._audit_service.log_action(
            stage=PipelineStage.ACQUISITION,
            action="PIPELINE_JOB_SUBMITTED",
            evidence_id=evidence_id,
            user_id=user_id,
            details={
                "job_id": job.job_id,
                "case_id": case_id,
                "mode": mode,
                "use_fallback": use_fallback,
            },
        )
        return job

    async def get_job(self, job_id: str) -> Optional[PipelineJob]:
        """Return a job by ID, or ``None`` if unknown."""
        return self._jobs.get(job_id)

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        case_id: Optional[str] = None,
    ) -> list[PipelineJob]:
        """List jobs, optionally filtered by status and/or case."""
        jobs = list(self._jobs.values())
        if status is not None:
            jobs = [job for job in jobs if job.status is status]
        if case_id is not None:
            jobs = [job for job in jobs if job.case_id == case_id]
        return sorted(jobs, key=lambda job: job.created_at)

    async def cancel_job(self, job_id: str, user_id: str) -> PipelineJob:
        """Cancel a QUEUED or RUNNING job.

        Args:
            job_id: Job identifier.
            user_id: Acting user identifier.

        Returns:
            Updated job with ``CANCELLED`` status.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobCancellationError: If the job is not cancellable.
        """
        job = self._require_job(job_id)
        if job.status not in _CANCELLABLE_STATUSES:
            raise JobCancellationError(
                f"Job cannot be cancelled in status {job.status.value}",
                context={"job_id": job_id, "status": job.status.value},
            )
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(UTC)
        if job.started_at is not None:
            job.total_duration_seconds = (
                job.completed_at - job.started_at
            ).total_seconds()
        await self._audit_service.log_action(
            stage=job.current_stage or PipelineStage.ACQUISITION,
            action="PIPELINE_JOB_CANCELLED",
            evidence_id=job.evidence_id,
            user_id=user_id,
            details={"job_id": job_id, "previous_cancellable": True},
        )
        return job

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error: Optional[str] = None,
    ) -> None:
        """Update a job's lifecycle status and optional error message."""
        job = self._require_job(job_id)
        now = datetime.now(UTC)
        job.status = status
        if error is not None:
            job.error_message = error
        if status is JobStatus.RUNNING and job.started_at is None:
            job.started_at = now
        if status in _TERMINAL_STATUSES:
            job.completed_at = now
            if job.started_at is not None:
                job.total_duration_seconds = (
                    job.completed_at - job.started_at
                ).total_seconds()

    async def update_stage(
        self,
        job_id: str,
        stage: PipelineStage,
        stage_execution: StageExecution,
    ) -> None:
        """Record a stage execution snapshot on the job."""
        job = self._require_job(job_id)
        job.current_stage = stage
        job.stage_executions[stage.value] = stage_execution
        if stage_execution.status.value == "completed":
            job.status = JobStatus.STAGE_COMPLETE

    async def get_active_job_count(self) -> int:
        """Return the number of non-terminal (active/queued) jobs."""
        return sum(1 for job in self._jobs.values() if job.status in _ACTIVE_STATUSES)

    async def cleanup_completed(self, older_than_hours: int = 24) -> int:
        """Remove terminal jobs older than the given age.

        Args:
            older_than_hours: Age threshold based on ``completed_at``
                (falls back to ``created_at``).

        Returns:
            Number of jobs removed.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        to_remove: list[str] = []
        for job_id, job in self._jobs.items():
            if job.status not in _TERMINAL_STATUSES:
                continue
            stamp = job.completed_at or job.created_at
            if stamp <= cutoff:
                to_remove.append(job_id)
        for job_id in to_remove:
            del self._jobs[job_id]
        return len(to_remove)

    def _require_job(self, job_id: str) -> PipelineJob:
        """Return a job or raise ``JobNotFoundError``."""
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(
                f"Pipeline job not found: {job_id}",
                context={"job_id": job_id},
            )
        return job
