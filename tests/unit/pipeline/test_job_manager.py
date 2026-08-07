"""Unit tests for JobManager in-memory job queue."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from dfat.pipeline.enums import JobStatus, StageStatus
from dfat.pipeline.job_manager import JobCancellationError, JobManager, JobNotFoundError
from dfat.pipeline.models import StageExecution
from dfat.core.enums import PipelineStage


@pytest.fixture
def job_manager() -> JobManager:
    """JobManager with a mocked audit service."""
    audit = AsyncMock()
    audit.log_action = AsyncMock()
    return JobManager(audit_service=audit, max_concurrent=2)


@pytest.mark.asyncio
async def test_submit_job_creates_queued_job(job_manager: JobManager) -> None:
    """Verify submit_job returns a QUEUED job and stores it."""
    # Arrange / Act
    job = await job_manager.submit_job(
        evidence_id="ev-1",
        case_id="case-1",
        user_id="user-1",
        mode="full",
        use_fallback=True,
    )

    # Assert
    assert job.status is JobStatus.QUEUED
    assert job.evidence_id == "ev-1"
    assert job.use_fallback_analyzer is True
    assert await job_manager.get_job(job.job_id) is job
    assert job_manager.max_concurrent == 2


@pytest.mark.asyncio
async def test_update_job_status_sets_timestamps(job_manager: JobManager) -> None:
    """Verify RUNNING sets started_at and COMPLETED sets duration."""
    # Arrange
    job = await job_manager.submit_job("ev-1", "case-1", "user-1")

    # Act
    await job_manager.update_job_status(job.job_id, JobStatus.RUNNING)
    running = await job_manager.get_job(job.job_id)
    await job_manager.update_job_status(job.job_id, JobStatus.COMPLETED)
    completed = await job_manager.get_job(job.job_id)

    # Assert
    assert running is not None and running.started_at is not None
    assert completed is not None
    assert completed.status is JobStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.total_duration_seconds is not None


@pytest.mark.asyncio
async def test_cancel_job_only_when_cancellable(job_manager: JobManager) -> None:
    """Verify cancel works for QUEUED and fails for COMPLETED."""
    # Arrange
    queued = await job_manager.submit_job("ev-1", "case-1", "user-1")
    done = await job_manager.submit_job("ev-2", "case-1", "user-1")
    await job_manager.update_job_status(done.job_id, JobStatus.COMPLETED)

    # Act
    cancelled = await job_manager.cancel_job(queued.job_id, "user-1")

    # Assert
    assert cancelled.status is JobStatus.CANCELLED
    with pytest.raises(JobCancellationError):
        await job_manager.cancel_job(done.job_id, "user-1")


@pytest.mark.asyncio
async def test_list_jobs_filters_by_status_and_case(job_manager: JobManager) -> None:
    """Verify list_jobs applies status and case_id filters."""
    # Arrange
    a = await job_manager.submit_job("ev-1", "case-a", "user-1")
    b = await job_manager.submit_job("ev-2", "case-b", "user-1")
    await job_manager.update_job_status(b.job_id, JobStatus.RUNNING)

    # Act / Assert
    assert len(await job_manager.list_jobs()) == 2
    assert len(await job_manager.list_jobs(status=JobStatus.QUEUED)) == 1
    assert len(await job_manager.list_jobs(case_id="case-a")) == 1
    assert (await job_manager.list_jobs(case_id="case-a"))[0].job_id == a.job_id


@pytest.mark.asyncio
async def test_unknown_job_raises_and_cleanup_works(job_manager: JobManager) -> None:
    """Verify JobNotFoundError and cleanup_completed remove old terminals."""
    # Arrange
    job = await job_manager.submit_job("ev-1", "case-1", "user-1")
    execution = StageExecution(
        stage=PipelineStage.PARSING,
        status=StageStatus.COMPLETED,
    )
    await job_manager.update_stage(job.job_id, PipelineStage.PARSING, execution)
    await job_manager.update_job_status(job.job_id, JobStatus.FAILED, error="boom")
    stored = await job_manager.get_job(job.job_id)
    assert stored is not None
    stored.completed_at = datetime.now(UTC) - timedelta(hours=48)

    # Act / Assert
    with pytest.raises(JobNotFoundError):
        await job_manager.update_job_status("missing", JobStatus.RUNNING)
    removed = await job_manager.cleanup_completed(older_than_hours=24)
    assert removed == 1
    assert await job_manager.get_job(job.job_id) is None
    assert await job_manager.get_active_job_count() == 0
