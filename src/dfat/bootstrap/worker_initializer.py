"""Background worker registration for FastAPI lifespan tasks."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import delete

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.database.models.session_orm import SessionORM
from dfat.runtime.task_manager import BackgroundTaskManager
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)

_AUTO_RETRAIN_INTERVAL_SECONDS = 3600
_HEALTH_CHECK_INTERVAL_SECONDS = 30
_SESSION_CLEANUP_INTERVAL_SECONDS = 3600
_CACHE_CLEANUP_INTERVAL_SECONDS = 1800


class WorkerInitializer:
    """Register periodic background tasks for the application lifespan."""

    def __init__(
        self,
        settings: DFATSettings,
        *,
        task_manager: BackgroundTaskManager | None = None,
        dataset_registry: Any | None = None,
        auto_retrainer: Any | None = None,
        llm_connection: Any | None = None,
        db_engine: Any | None = None,
        session_repo: Any | None = None,
        ai_response_cache: Any | None = None,
    ) -> None:
        self._settings = settings
        self.task_manager = task_manager or BackgroundTaskManager()
        self._dataset_registry = dataset_registry
        self._auto_retrainer = auto_retrainer
        self._llm_connection = llm_connection
        self._db_engine = db_engine
        self._session_repo = session_repo
        self._ai_response_cache = ai_response_cache

    async def initialize(self) -> PhaseResult:
        """Register background tasks to run within FastAPI's lifespan.

        Returns:
            ``PhaseResult`` with ``COMPLETED`` and registered task names.
        """
        started = time.perf_counter()
        watch_interval = self._settings.dataset_intelligence.watch_interval_seconds
        registered: list[str] = []

        self.task_manager.register(
            "DatasetWatcher",
            self._dataset_watch_tick,
            watch_interval,
        )
        registered.append("DatasetWatcher")

        self.task_manager.register(
            "AutoRetrainer",
            self._auto_retrain_tick,
            _AUTO_RETRAIN_INTERVAL_SECONDS,
        )
        registered.append("AutoRetrainer")

        self.task_manager.register(
            "HealthMonitor",
            self._health_monitor_tick,
            _HEALTH_CHECK_INTERVAL_SECONDS,
        )
        registered.append("HealthMonitor")

        self.task_manager.register(
            "SessionCleanup",
            self._session_cleanup_tick,
            _SESSION_CLEANUP_INTERVAL_SECONDS,
        )
        registered.append("SessionCleanup")

        self.task_manager.register(
            "CacheCleanup",
            self._cache_cleanup_tick,
            _CACHE_CLEANUP_INTERVAL_SECONDS,
        )
        registered.append("CacheCleanup")

        duration_ms = (time.perf_counter() - started) * 1000.0
        return PhaseResult(
            phase=InitPhase.BACKGROUND_WORKERS,
            status=InitStatus.COMPLETED,
            duration_ms=duration_ms,
            message=f"Registered {len(registered)} background worker(s)",
            details={
                "registered_tasks": registered,
                "intervals": {
                    "DatasetWatcher": watch_interval,
                    "AutoRetrainer": _AUTO_RETRAIN_INTERVAL_SECONDS,
                    "HealthMonitor": _HEALTH_CHECK_INTERVAL_SECONDS,
                    "SessionCleanup": _SESSION_CLEANUP_INTERVAL_SECONDS,
                    "CacheCleanup": _CACHE_CLEANUP_INTERVAL_SECONDS,
                },
            },
            is_critical=False,
        )

    async def _dataset_watch_tick(self) -> None:
        if self._dataset_registry is None:
            logger.debug("DatasetWatcher skipped — registry not configured")
            return
        await self._dataset_registry.register_all()

    async def _auto_retrain_tick(self) -> None:
        if self._auto_retrainer is None:
            logger.debug("AutoRetrainer skipped — retrainer not configured")
            return
        retrained = await self._auto_retrainer.check_and_retrain()
        if retrained:
            logger.info("Auto-retrained model(s): %s", ", ".join(retrained))

    async def _health_monitor_tick(self) -> None:
        details: dict[str, Any] = {}

        if self._db_engine is not None:
            try:
                details["database"] = await self._db_engine.check_connection()
            except Exception as exc:  # noqa: BLE001
                details["database"] = False
                details["database_error"] = str(exc)
                logger.warning("HealthMonitor database check failed: %s", exc)

        if self._llm_connection is not None:
            try:
                health = await self._llm_connection.check_health()
                details["llm"] = getattr(health, "is_healthy", False)
            except Exception as exc:  # noqa: BLE001
                details["llm"] = False
                details["llm_error"] = str(exc)
                logger.warning("HealthMonitor LLM check failed: %s", exc)

        if details:
            logger.debug("HealthMonitor snapshot: %s", details)

    async def _session_cleanup_tick(self) -> None:
        removed = await self._cleanup_expired_sessions()
        if removed:
            logger.info("SessionCleanup removed %d expired session(s)", removed)

    async def _cache_cleanup_tick(self) -> None:
        if self._ai_response_cache is None:
            logger.debug("CacheCleanup skipped — AI response cache not configured")
            return
        evict = getattr(self._ai_response_cache, "evict_expired", None)
        if evict is None:
            logger.debug("CacheCleanup skipped — cache has no evict_expired()")
            return
        removed = await evict()
        if removed:
            logger.info("CacheCleanup evicted %d stale cache entry/entries", removed)

    async def _cleanup_expired_sessions(self) -> int:
        """Remove sessions expired beyond the seven-day retention window."""
        if self._session_repo is not None:
            factory = getattr(self._session_repo, "_session_factory", None)
            if factory is not None:
                cutoff = datetime.now(UTC) - timedelta(days=7)
                async with factory() as session:
                    result = await session.execute(
                        delete(SessionORM).where(SessionORM.expires_at < cutoff)
                    )
                    await session.commit()
                    return int(result.rowcount or 0)
            cleanup = getattr(self._session_repo, "cleanup_expired", None)
            if cleanup is not None:
                return int(await cleanup())

        if self._db_engine is None:
            return 0

        factory = getattr(self._db_engine, "session_factory", None)
        if factory is None:
            return 0

        cutoff = datetime.now(UTC) - timedelta(days=7)
        async with factory() as session:
            result = await session.execute(
                delete(SessionORM).where(SessionORM.expires_at < cutoff)
            )
            await session.commit()
            return int(result.rowcount or 0)
