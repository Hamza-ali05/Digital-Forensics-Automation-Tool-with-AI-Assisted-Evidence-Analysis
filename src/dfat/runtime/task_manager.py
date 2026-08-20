"""Background task scheduling for the FastAPI application lifecycle."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_DEFAULT_STOP_TIMEOUT_SECONDS = 5.0


class TaskStatus(BaseModel):
    """Runtime status for a registered background task."""

    model_config = ConfigDict(validate_assignment=True)

    name: str
    is_running: bool = False
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    interval_seconds: int = Field(ge=0)


@dataclass
class _RegisteredTask:
    """Internal registration record for a periodic background task."""

    name: str
    coroutine: Callable[[], Awaitable[None]]
    interval_seconds: int
    status: TaskStatus = field(init=False)

    def __post_init__(self) -> None:
        self.status = TaskStatus(name=self.name, interval_seconds=self.interval_seconds)


class BackgroundTaskManager:
    """Manage long-running periodic tasks within the FastAPI lifecycle."""

    def __init__(self, stop_timeout_seconds: float = _DEFAULT_STOP_TIMEOUT_SECONDS) -> None:
        self._stop_timeout_seconds = stop_timeout_seconds
        self._registrations: dict[str, _RegisteredTask] = {}
        self._async_tasks: dict[str, asyncio.Task[None]] = {}
        self._stop_event = asyncio.Event()

    def register(
        self,
        name: str,
        coroutine: Callable[[], Awaitable[None]],
        interval_seconds: int,
    ) -> None:
        """Register a periodic task.

        Args:
            name: Unique task identifier.
            coroutine: Zero-argument async callable executed each cycle.
            interval_seconds: Delay between runs.
        """
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be >= 0")
        if name in self._registrations:
            raise ValueError(f"Task already registered: {name}")
        self._registrations[name] = _RegisteredTask(
            name=name,
            coroutine=coroutine,
            interval_seconds=interval_seconds,
        )

    async def start_all(self) -> None:
        """Start every registered task as an asyncio background task."""
        if self._async_tasks:
            return
        self._stop_event.clear()
        for registration in self._registrations.values():
            task = asyncio.create_task(
                self._run_loop(registration),
                name=f"dfat-bg-{registration.name}",
            )
            self._async_tasks[registration.name] = task
        logger.info("Started %d background task(s)", len(self._async_tasks))

    async def stop_all(self) -> None:
        """Cancel all running tasks and wait for graceful shutdown."""
        if not self._async_tasks:
            return

        self._stop_event.set()
        tasks = list(self._async_tasks.values())
        for task in tasks:
            task.cancel()

        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self._stop_timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "Background task shutdown timed out after %.1fs",
                self._stop_timeout_seconds,
            )

        for registration in self._registrations.values():
            registration.status.is_running = False
            registration.status.next_run = None

        self._async_tasks.clear()
        logger.info("Stopped background tasks")

    def get_task_status(self) -> dict[str, TaskStatus]:
        """Return a snapshot of every registered task's runtime status."""
        return {name: reg.status.model_copy(deep=True) for name, reg in self._registrations.items()}

    async def restart_task(self, name: str) -> TaskStatus:
        """Stop and restart a single background task by name."""
        if name not in self._registrations:
            raise KeyError(f"Unknown background task: {name}")
        if self._stop_event.is_set():
            raise RuntimeError("Cannot restart tasks during shutdown")

        registration = self._registrations[name]
        existing = self._async_tasks.get(name)
        if existing is not None:
            existing.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.gather(existing, return_exceptions=True),
                    timeout=self._stop_timeout_seconds,
                )
            except TimeoutError:
                logger.warning(
                    "Restart of task %s timed out after %.1fs",
                    name,
                    self._stop_timeout_seconds,
                )
            self._async_tasks.pop(name, None)

        registration.status.is_running = False
        registration.status.next_run = None
        task = asyncio.create_task(
            self._run_loop(registration),
            name=f"dfat-bg-{registration.name}",
        )
        self._async_tasks[name] = task
        logger.info("Restarted background task: %s", name)
        return registration.status.model_copy(deep=True)

    async def _run_loop(self, registration: _RegisteredTask) -> None:
        status = registration.status
        status.is_running = True
        try:
            while not self._stop_event.is_set():
                status.next_run = datetime.now(UTC) + timedelta(
                    seconds=registration.interval_seconds
                )
                try:
                    await registration.coroutine()
                    status.run_count += 1
                    status.last_run = datetime.now(UTC)
                    status.last_error = None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    status.error_count += 1
                    status.last_error = str(exc)
                    logger.exception("Background task %s failed", registration.name)

                if self._stop_event.is_set():
                    break

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=registration.interval_seconds,
                    )
                    break
                except TimeoutError:
                    continue
        finally:
            status.is_running = False
            status.next_run = None
