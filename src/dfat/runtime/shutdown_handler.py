"""Graceful application shutdown for background tasks and persistence."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any, Optional

from dfat.core.enums import PipelineStage
from dfat.database.engine import DatabaseEngine
from dfat.pipeline.enums import JobStatus
from dfat.runtime.task_manager import BackgroundTaskManager
from dfat.services.audit_service import AuditService

logger = logging.getLogger(__name__)

_TASK_STOP_TIMEOUT_SECONDS = 10.0
_PIPELINE_WAIT_TIMEOUT_SECONDS = 60.0
_PIPELINE_POLL_INTERVAL_SECONDS = 0.5

_ACTIVE_JOB_STATUSES = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.INITIALISING,
        JobStatus.RUNNING,
        JobStatus.STAGE_COMPLETE,
    }
)


class ShutdownHandler:
    """Coordinate graceful shutdown of workers, pipelines, audit, and database."""

    def __init__(
        self,
        task_manager: BackgroundTaskManager,
        db_engine: DatabaseEngine,
        audit_service: AuditService,
        job_manager: Any | None = None,
        *,
        task_stop_timeout_seconds: float = _TASK_STOP_TIMEOUT_SECONDS,
        pipeline_wait_timeout_seconds: float = _PIPELINE_WAIT_TIMEOUT_SECONDS,
    ) -> None:
        self._task_manager = task_manager
        self._db_engine = db_engine
        self._audit_service = audit_service
        self._job_manager = job_manager
        self._task_stop_timeout_seconds = task_stop_timeout_seconds
        self._pipeline_wait_timeout_seconds = pipeline_wait_timeout_seconds
        self._shutting_down = False
        self._signal_handlers_registered = False

    async def shutdown(self) -> None:
        """Stop workers, drain pipelines, flush audit logs, and release resources."""
        if self._shutting_down:
            return
        self._shutting_down = True

        logger.info("DFAT shutdown initiated")
        try:
            await self._audit_service.log_action(
                stage=PipelineStage.ACQUISITION,
                action="SYSTEM_SHUTDOWN_INITIATED",
                evidence_id="system",
                details={},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not log shutdown initiation audit entry: %s", exc)

        original_stop_timeout = self._task_manager._stop_timeout_seconds
        self._task_manager._stop_timeout_seconds = self._task_stop_timeout_seconds
        try:
            await self._task_manager.stop_all()
        finally:
            self._task_manager._stop_timeout_seconds = original_stop_timeout

        await self._wait_for_active_pipeline_jobs()
        await self._flush_audit_buffers()

        try:
            await self._db_engine.dispose()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Database dispose during shutdown failed: %s", exc)

        try:
            await self._audit_service.log_action(
                stage=PipelineStage.ACQUISITION,
                action="SYSTEM_SHUTDOWN_COMPLETED",
                evidence_id="system",
                details={},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not log shutdown completion audit entry: %s", exc)

        logger.info("DFAT shutdown complete")

    def register_signal_handlers(
        self,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """Register ``SIGTERM`` and ``SIGINT`` handlers that trigger shutdown."""
        if self._signal_handlers_registered:
            return

        event_loop = loop or asyncio.get_event_loop()

        def _schedule_shutdown() -> None:
            asyncio.create_task(self.shutdown())

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                event_loop.add_signal_handler(sig, _schedule_shutdown)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, lambda _signum, _frame: _schedule_shutdown())

        self._signal_handlers_registered = True
        logger.debug("Registered SIGTERM/SIGINT shutdown handlers")

    async def _wait_for_active_pipeline_jobs(self) -> None:
        if self._job_manager is None:
            return

        deadline = asyncio.get_running_loop().time() + self._pipeline_wait_timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            active = _count_active_jobs(self._job_manager)
            if active == 0:
                return
            await asyncio.sleep(_PIPELINE_POLL_INTERVAL_SECONDS)

        remaining = _count_active_jobs(self._job_manager)
        if remaining:
            logger.warning(
                "Shutdown proceeding with %d active pipeline job(s) after %.0fs timeout",
                remaining,
                self._pipeline_wait_timeout_seconds,
            )

    async def _flush_audit_buffers(self) -> None:
        flush = getattr(self._audit_service, "flush", None)
        if flush is not None:
            result = flush()
            if asyncio.iscoroutine(result):
                await result
            return

        file_logger = getattr(self._audit_service, "_file_logger", None)
        file_flush = getattr(file_logger, "flush", None)
        if callable(file_flush):
            file_flush()


def _count_active_jobs(job_manager: Any) -> int:
    jobs = getattr(job_manager, "_jobs", {})
    return sum(
        1
        for job in jobs.values()
        if getattr(job, "status", None) in _ACTIVE_JOB_STATUSES
    )
