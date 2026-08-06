"""Performance timing utilities for time-to-triage measurement."""

from __future__ import annotations

import time
from types import TracebackType
from typing import Optional


class PerformanceTimer:
    """Context manager that records wall-clock elapsed time.

    Example:
        with PerformanceTimer() as timer:
            do_work()
        print(timer.elapsed_seconds)
    """

    def __init__(self) -> None:
        """Initialise an unstarted timer."""
        self._start: Optional[float] = None
        self._end: Optional[float] = None

    def __enter__(self) -> PerformanceTimer:
        """Start timing on context entry.

        Returns:
            This timer instance.
        """
        self._start = time.perf_counter()
        self._end = None
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Stop timing on context exit."""
        self._end = time.perf_counter()

    @property
    def elapsed_seconds(self) -> float:
        """Return elapsed seconds since start (or until stop if exited).

        Returns:
            Elapsed wall-clock seconds.

        Raises:
            RuntimeError: If the timer has not been started.
        """
        if self._start is None:
            raise RuntimeError("PerformanceTimer has not been started")
        end = self._end if self._end is not None else time.perf_counter()
        return end - self._start
