"""Filesystem watcher that periodically registers new or changed datasets."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

from dfat.core.enums import PipelineStage
from dfat.dataset_intelligence.config import DatasetIntelligenceSettings


class DatasetWatcher:
    """Poll the datasets directory for new or modified files."""

    def __init__(self, settings: DatasetIntelligenceSettings, registry, audit_service) -> None:
        self._settings = settings
        self._registry = registry
        self._audit_service = audit_service
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._known_mtimes: dict[str, float] = {}

    async def start(self) -> None:
        """Start the background polling task if enabled and not already running."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._known_mtimes = await asyncio.to_thread(self._snapshot_mtimes)
        self._task = asyncio.create_task(self._run(), name="dataset-watcher")
        await self._audit_service.log_action(
            stage=PipelineStage.EVALUATION,
            action="DATASET_WATCHER_STARTED",
            evidence_id="dataset_watcher",
            details={"watch_path": str(self._settings.datasets_dir)},
        )

    async def stop(self) -> None:
        """Stop the background polling task."""
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None
        await self._audit_service.log_action(
            stage=PipelineStage.EVALUATION,
            action="DATASET_WATCHER_STOPPED",
            evidence_id="dataset_watcher",
            details={"stopped_at": datetime.now(UTC).isoformat()},
        )

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                current = await asyncio.to_thread(self._snapshot_mtimes)
                changed_paths = [
                    path
                    for path, mtime in current.items()
                    if self._known_mtimes.get(path) != mtime
                ]
                for path in changed_paths:
                    await self._registry.register_single(Path(path))
                self._known_mtimes = current
            except Exception:  # noqa: BLE001
                # Keep the watcher alive; errors are surfaced by subsequent polls.
                pass

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._settings.watch_interval_seconds,
                )
            except TimeoutError:
                continue

    def _snapshot_mtimes(self) -> dict[str, float]:
        base_path = Path(self._settings.datasets_dir)
        if not base_path.exists() or not base_path.is_dir():
            return {}

        snapshot: dict[str, float] = {}
        for root, dirs, files in os.walk(base_path, topdown=True, followlinks=False):
            dirs[:] = [
                name
                for name in dirs
                if not name.startswith(".")
                and name not in {"__pycache__", ".git", "node_modules"}
            ]
            for file_name in files:
                if file_name.startswith("."):
                    continue
                path = Path(root) / file_name
                if path.is_symlink():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                snapshot[str(path)] = stat.st_mtime
        return snapshot
