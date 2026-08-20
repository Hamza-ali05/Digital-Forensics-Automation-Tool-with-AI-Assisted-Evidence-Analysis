"""Unit tests for graceful ShutdownHandler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import PipelineStage
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.models import PipelineJob
from dfat.runtime.shutdown_handler import ShutdownHandler
from dfat.runtime.task_manager import BackgroundTaskManager


@pytest.mark.asyncio
async def test_shutdown_logs_audit_entries() -> None:
    audit_service = AsyncMock()
    audit_service.flush = AsyncMock()
    task_manager = BackgroundTaskManager()
    task_manager.stop_all = AsyncMock()
    db_engine = AsyncMock()
    db_engine.dispose = AsyncMock()
    handler = ShutdownHandler(
        task_manager=task_manager,
        db_engine=db_engine,
        audit_service=audit_service,
    )

    await handler.shutdown()

    actions = [call.kwargs["action"] for call in audit_service.log_action.await_args_list]
    assert actions == ["SYSTEM_SHUTDOWN_INITIATED", "SYSTEM_SHUTDOWN_COMPLETED"]
    assert all(
        call.kwargs["stage"] == PipelineStage.ACQUISITION
        for call in audit_service.log_action.await_args_list
    )


@pytest.mark.asyncio
async def test_shutdown_stops_background_tasks_gracefully() -> None:
    audit_service = AsyncMock()
    audit_service.flush = AsyncMock()
    task_manager = BackgroundTaskManager()
    task_manager.stop_all = AsyncMock()
    db_engine = AsyncMock()
    db_engine.dispose = AsyncMock()
    handler = ShutdownHandler(
        task_manager=task_manager,
        db_engine=db_engine,
        audit_service=audit_service,
        task_stop_timeout_seconds=10.0,
    )

    await handler.shutdown()

    task_manager.stop_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_flushes_audit_buffers() -> None:
    audit_service = AsyncMock()
    audit_service.flush = AsyncMock()
    task_manager = BackgroundTaskManager()
    task_manager.stop_all = AsyncMock()
    db_engine = AsyncMock()
    db_engine.dispose = AsyncMock()
    handler = ShutdownHandler(
        task_manager=task_manager,
        db_engine=db_engine,
        audit_service=audit_service,
    )

    await handler.shutdown()

    audit_service.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_waits_for_active_pipeline_jobs() -> None:
    audit_service = AsyncMock()
    audit_service.flush = AsyncMock()
    task_manager = BackgroundTaskManager()
    task_manager.stop_all = AsyncMock()
    db_engine = AsyncMock()
    db_engine.dispose = AsyncMock()

    running_job = PipelineJob(
        evidence_id="ev-1",
        case_id="case-1",
        user_id="user-1",
        status=JobStatus.RUNNING,
    )
    completed_job = PipelineJob(
        evidence_id="ev-2",
        case_id="case-1",
        user_id="user-1",
        status=JobStatus.COMPLETED,
    )
    job_manager = MagicMock(
        _jobs={
            "active": running_job,
            "done": completed_job,
        }
    )

    async def complete_job_after_delay() -> None:
        import asyncio

        await asyncio.sleep(0.05)
        running_job.status = JobStatus.COMPLETED

    handler = ShutdownHandler(
        task_manager=task_manager,
        db_engine=db_engine,
        audit_service=audit_service,
        job_manager=job_manager,
        pipeline_wait_timeout_seconds=2.0,
    )

    import asyncio

    await asyncio.gather(handler.shutdown(), complete_job_after_delay())

    db_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_is_idempotent() -> None:
    audit_service = AsyncMock()
    audit_service.flush = AsyncMock()
    task_manager = BackgroundTaskManager()
    task_manager.stop_all = AsyncMock()
    db_engine = AsyncMock()
    db_engine.dispose = AsyncMock()
    handler = ShutdownHandler(
        task_manager=task_manager,
        db_engine=db_engine,
        audit_service=audit_service,
    )

    await handler.shutdown()
    await handler.shutdown()

    assert task_manager.stop_all.await_count == 1
    assert db_engine.dispose.await_count == 1
