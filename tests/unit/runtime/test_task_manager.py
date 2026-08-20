"""Unit tests for BackgroundTaskManager and WorkerInitializer."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.bootstrap.models import InitPhase, InitStatus
from dfat.bootstrap.worker_initializer import (
    WorkerInitializer,
    _AUTO_RETRAIN_INTERVAL_SECONDS,
    _CACHE_CLEANUP_INTERVAL_SECONDS,
    _HEALTH_CHECK_INTERVAL_SECONDS,
    _SESSION_CLEANUP_INTERVAL_SECONDS,
)
from dfat.runtime.task_manager import BackgroundTaskManager, TaskStatus
from dfat.settings import load_settings


@pytest.mark.asyncio
async def test_task_manager_registers_and_starts() -> None:
    manager = BackgroundTaskManager()
    runs = {"count": 0}

    async def tick() -> None:
        runs["count"] += 1

    manager.register("probe", tick, interval_seconds=0)
    await manager.start_all()
    await asyncio.sleep(0.05)
    await manager.stop_all()

    assert runs["count"] >= 1
    status = manager.get_task_status()["probe"]
    assert status.run_count >= 1
    assert status.is_running is False


@pytest.mark.asyncio
async def test_task_manager_stop_is_graceful() -> None:
    manager = BackgroundTaskManager(stop_timeout_seconds=2.0)
    started = asyncio.Event()
    release = asyncio.Event()

    async def long_tick() -> None:
        started.set()
        await release.wait()

    manager.register("long", long_tick, interval_seconds=60)
    await manager.start_all()
    await asyncio.wait_for(started.wait(), timeout=1.0)

    stop_task = asyncio.create_task(manager.stop_all())
    await asyncio.sleep(0.01)
    release.set()
    await asyncio.wait_for(stop_task, timeout=2.0)

    status = manager.get_task_status()["long"]
    assert status.is_running is False


@pytest.mark.asyncio
async def test_task_manager_respects_interval() -> None:
    manager = BackgroundTaskManager()
    runs: list[float] = []

    async def tick() -> None:
        runs.append(asyncio.get_running_loop().time())

    manager.register("interval", tick, interval_seconds=1)
    await manager.start_all()
    await asyncio.sleep(2.1)
    await manager.stop_all()

    assert len(runs) >= 2
    gap = runs[1] - runs[0]
    assert gap >= 0.9


@pytest.mark.asyncio
async def test_task_manager_records_errors() -> None:
    manager = BackgroundTaskManager()

    async def failing_tick() -> None:
        raise RuntimeError("boom")

    manager.register("fail", failing_tick, interval_seconds=0)
    await manager.start_all()
    await asyncio.sleep(0.05)
    await manager.stop_all()

    status = manager.get_task_status()["fail"]
    assert status.error_count >= 1
    assert status.last_error == "boom"


def test_task_status_model_fields() -> None:
    status = TaskStatus(
        name="demo",
        is_running=True,
        last_run=datetime.now(UTC),
        next_run=datetime.now(UTC),
        run_count=3,
        error_count=1,
        last_error="err",
        interval_seconds=30,
    )
    assert status.name == "demo"
    assert status.interval_seconds == 30


@pytest.mark.asyncio
async def test_worker_initializer_registers_all_tasks() -> None:
    settings = load_settings(env="development")
    manager = BackgroundTaskManager()
    initializer = WorkerInitializer(settings, task_manager=manager)

    result = await initializer.initialize()

    assert result.phase == InitPhase.BACKGROUND_WORKERS
    assert result.status == InitStatus.COMPLETED
    assert len(result.details["registered_tasks"]) == 5
    assert manager.get_task_status()["DatasetWatcher"].interval_seconds == (
        settings.dataset_intelligence.watch_interval_seconds
    )
    assert manager.get_task_status()["AutoRetrainer"].interval_seconds == (
        _AUTO_RETRAIN_INTERVAL_SECONDS
    )
    assert manager.get_task_status()["HealthMonitor"].interval_seconds == (
        _HEALTH_CHECK_INTERVAL_SECONDS
    )
    assert manager.get_task_status()["SessionCleanup"].interval_seconds == (
        _SESSION_CLEANUP_INTERVAL_SECONDS
    )
    assert manager.get_task_status()["CacheCleanup"].interval_seconds == (
        _CACHE_CLEANUP_INTERVAL_SECONDS
    )


@pytest.mark.asyncio
async def test_worker_initializer_tasks_execute_with_dependencies() -> None:
    settings = load_settings(env="development")
    manager = BackgroundTaskManager()
    registry = AsyncMock()
    registry.register_all.return_value = MagicMock(datasets=[])

    retrainer = AsyncMock()
    retrainer.check_and_retrain.return_value = ["MalwareClassifier"]

    llm = AsyncMock()
    llm.check_health.return_value = MagicMock(is_healthy=True)

    cache = AsyncMock()
    cache.evict_expired.return_value = 2

    initializer = WorkerInitializer(
        settings,
        task_manager=manager,
        dataset_registry=registry,
        auto_retrainer=retrainer,
        llm_connection=llm,
        ai_response_cache=cache,
    )
    await initializer.initialize()

    await manager.start_all()
    await asyncio.sleep(0.08)
    await manager.stop_all()

    assert registry.register_all.await_count >= 1
