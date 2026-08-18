"""Extended orchestration and cancellation tests with fake stages."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import PipelineStage
from dfat.core.models.evidence import EvidenceImage
from dfat.core.models.pipeline import StageResult
from dfat.pipeline.enums import JobStatus, StageStatus
from dfat.pipeline.job_manager import JobCancellationError, JobManager
from dfat.pipeline.job_runner import JobRunner
from dfat.pipeline.orchestrator import PipelineOrchestrator
from dfat.pipeline.progress_tracker import ProgressTracker
from dfat.pipeline.stage_interface import IPipelineStage, PipelineContext
from dfat.pipeline.stage_registry import StageRegistry


class FakeStage(IPipelineStage):
    def __init__(self, stage: PipelineStage, hook=None) -> None:
        self._stage = stage
        self._hook = hook

    @property
    def stage_name(self) -> PipelineStage:
        return self._stage

    @property
    def description(self) -> str:
        return f"Fake {self._stage.value}"

    async def validate_preconditions(self, context: PipelineContext) -> bool:
        return True

    async def execute(self, context: PipelineContext) -> StageResult:
        if self._hook is not None:
            value = self._hook(context)
            if value is not None:
                await value
        return StageResult(
            stage=self._stage,
            success=True,
            duration_seconds=0.001,
            output_data={"stage": self._stage.value},
        )


def _orchestrator(
    evidence: EvidenceImage, *, first_hook=None
) -> tuple[PipelineOrchestrator, JobManager]:
    audit = MagicMock()
    audit.log_action = AsyncMock()
    registry = StageRegistry()
    for index, stage in enumerate(PipelineStage):
        registry.register(FakeStage(stage, first_hook if index == 0 else None))
    manager = JobManager(audit_service=audit, max_concurrent=2)
    runner = JobRunner(manager, registry, audit)
    evidence_repo = MagicMock()
    evidence_repo.get = AsyncMock(return_value=evidence)
    case_repo = MagicMock()
    case_repo.get = AsyncMock(return_value=None)
    pipeline_logger = MagicMock()
    pipeline_logger.log_job_start = AsyncMock()
    evidence_mgmt = MagicMock()
    evidence_mgmt.transition_evidence_status = AsyncMock()
    custody = MagicMock()
    custody.record_analysis = AsyncMock()
    orchestrator = PipelineOrchestrator(
        stage_registry=registry,
        job_manager=manager,
        job_runner=runner,
        progress_tracker=ProgressTracker(),
        pipeline_logger=pipeline_logger,
        evidence_repo=evidence_repo,
        case_repo=case_repo,
        audit_service=audit,
        settings=MagicMock(),
        evidence_management_service=evidence_mgmt,
        custody_service=custody,
        ground_truth_loader=MagicMock(),
        benchmark_comparator=MagicMock(),
    )
    return orchestrator, manager


@pytest.mark.asyncio
async def test_execute_pipeline_runs_all_five_stages_with_fallback(
    sample_evidence_image: EvidenceImage,
) -> None:
    # Arrange
    orchestrator, _manager = _orchestrator(sample_evidence_image)

    # Act
    job = await orchestrator.execute_pipeline(
        sample_evidence_image.evidence_id,
        sample_evidence_image.case.case_id,
        "u1",
        use_fallback=True,
    )

    # Assert
    assert job.status is JobStatus.COMPLETED
    assert job.use_fallback_analyzer is True
    assert set(job.stage_executions) == {stage.value for stage in PipelineStage}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.RUNNING])
async def test_cancel_pipeline_cancels_queued_or_running_job(
    sample_evidence_image: EvidenceImage, status: JobStatus
) -> None:
    # Arrange
    orchestrator, manager = _orchestrator(sample_evidence_image)
    job = await orchestrator.submit_pipeline(
        sample_evidence_image.evidence_id,
        sample_evidence_image.case.case_id,
        "u1",
    )
    if status is JobStatus.RUNNING:
        await manager.update_job_status(job.job_id, JobStatus.RUNNING)

    # Act
    cancelled = await orchestrator.cancel_pipeline(job.job_id, "u1")

    # Assert
    assert cancelled.status is JobStatus.CANCELLED
    assert cancelled.completed_at is not None


@pytest.mark.asyncio
async def test_cancelling_completed_job_raises(
    sample_evidence_image: EvidenceImage,
) -> None:
    # Arrange
    _orchestrator_instance, manager = _orchestrator(sample_evidence_image)
    job = await manager.submit_job("ev-1", "case-1", "u1")
    await manager.update_job_status(job.job_id, JobStatus.COMPLETED)

    # Act / Assert
    with pytest.raises(JobCancellationError):
        await manager.cancel_job(job.job_id, "u1")


@pytest.mark.asyncio
async def test_mid_stage_cancellation_stops_before_next_stage(
    sample_evidence_image: EvidenceImage,
) -> None:
    # Arrange
    orchestrator, manager = _orchestrator(sample_evidence_image)
    original_update_stage = manager.update_stage
    cancellation_applied = False

    async def cancel_between_stages(job_id, stage, execution):
        nonlocal cancellation_applied
        await original_update_stage(job_id, stage, execution)
        if execution.status is StageStatus.COMPLETED and not cancellation_applied:
            cancellation_applied = True
            await manager.update_job_status(job_id, JobStatus.CANCELLED)

    manager.update_stage = cancel_between_stages  # type: ignore[method-assign]

    # Act
    job = await orchestrator.execute_pipeline(
        sample_evidence_image.evidence_id,
        sample_evidence_image.case.case_id,
        "u1",
    )

    # Assert
    assert job.status is JobStatus.CANCELLED
    assert set(job.stage_executions) == {PipelineStage.ACQUISITION.value}
