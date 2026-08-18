"""SQLAlchemy slow-query monitoring for DFAT persistence.

``QueryMonitor`` attaches engine-level cursor event listeners (the SQLAlchemy
equivalent of query middleware) and logs statements whose duration exceeds a
configurable threshold, including the calling application function when it can
be recovered from the stack.
"""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any, Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

_LOGGER = logging.getLogger(__name__)

_INTERNAL_MODULE_PREFIXES = (
    "sqlalchemy",
    "aiosqlite",
    "greenlet",
    "asyncio",
    "logging",
    "dfat.database.query_monitor",
)


def _sync_engine(engine: AsyncEngine | Engine) -> Engine:
    """Return the synchronous engine wrapped by an async engine, if any."""
    if isinstance(engine, AsyncEngine):
        return engine.sync_engine
    return engine


def _calling_function() -> str:
    """Best-effort application frame for the current SQL execution."""
    for frame_info in inspect.stack()[1:]:
        module = frame_info.frame.f_globals.get("__name__", "")
        if any(module.startswith(prefix) for prefix in _INTERNAL_MODULE_PREFIXES):
            continue
        if not module:
            continue
        return f"{module}.{frame_info.function}"
    return "<unknown>"


class QueryMonitor:
    """Middleware that logs SQL statements slower than a duration threshold.

    Uses SQLAlchemy ``before_cursor_execute`` / ``after_cursor_execute``
    listeners so it works for both sync and async engines.
    """

    def __init__(
        self,
        threshold_ms: int = 100,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Initialise the monitor.

        Args:
            threshold_ms: Minimum duration in milliseconds before a query is
                logged as slow.
            logger: Optional logger override (defaults to this module).
        """
        self.threshold_ms = max(0, int(threshold_ms))
        self._logger = logger or _LOGGER
        self._engines: list[Engine] = []

    def attach(self, engine: AsyncEngine | Engine) -> None:
        """Register cursor listeners on ``engine``.

        Args:
            engine: Async or sync SQLAlchemy engine.
        """
        sync_engine = _sync_engine(engine)
        if sync_engine in self._engines:
            return
        event.listen(sync_engine, "before_cursor_execute", self._before_cursor_execute)
        event.listen(sync_engine, "after_cursor_execute", self._after_cursor_execute)
        self._engines.append(sync_engine)

    def detach(self, engine: AsyncEngine | Engine | None = None) -> None:
        """Remove cursor listeners from one engine, or all attached engines.

        Args:
            engine: Engine to detach. When omitted, every attached engine is
                detached.
        """
        targets = [_sync_engine(engine)] if engine is not None else list(self._engines)
        for sync_engine in targets:
            try:
                event.remove(
                    sync_engine,
                    "before_cursor_execute",
                    self._before_cursor_execute,
                )
                event.remove(
                    sync_engine,
                    "after_cursor_execute",
                    self._after_cursor_execute,
                )
            except Exception:  # noqa: BLE001 — listener may already be gone
                pass
            if sync_engine in self._engines:
                self._engines.remove(sync_engine)

    def _before_cursor_execute(
        self,
        _conn: Any,
        _cursor: Any,
        _statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        """Record query start time on the execution context."""
        context._dfat_query_start = time.perf_counter()

    def _after_cursor_execute(
        self,
        _conn: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        """Log the statement when elapsed time meets the slow-query threshold."""
        started = getattr(context, "_dfat_query_start", None)
        if started is None:
            return
        duration_ms = (time.perf_counter() - started) * 1000.0
        if duration_ms < self.threshold_ms:
            return
        caller = _calling_function()
        self._logger.warning(
            "Slow query (%.1fms) in %s: %s",
            duration_ms,
            caller,
            " ".join(statement.split()),
        )
