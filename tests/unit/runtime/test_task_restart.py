"""Unit tests for BackgroundTaskManager.restart_task."""

from __future__ import annotations

import asyncio

import pytest

from dfat.runtime.task_manager import BackgroundTaskManager


@pytest.mark.asyncio
async def test_restart_task_restarts_named_worker() -> None:
    manager = BackgroundTaskManager()
    runs = {"count": 0}

    async def tick() -> None:
        runs["count"] += 1

    manager.register("worker", tick, interval_seconds=0)
    await manager.start_all()
    await asyncio.sleep(0.05)
    first_count = runs["count"]
    assert first_count >= 1

    status = await manager.restart_task("worker")
    await asyncio.sleep(0.05)
    await manager.stop_all()

    assert runs["count"] > first_count
    assert status.name == "worker"


@pytest.mark.asyncio
async def test_restart_unknown_task_raises_key_error() -> None:
    manager = BackgroundTaskManager()

    with pytest.raises(KeyError, match="Unknown background task"):
        await manager.restart_task("missing")
