"""Runtime metrics collection for the monitoring dashboard."""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

from pydantic import BaseModel


class MetricsSummary(BaseModel):
    """Snapshot of runtime metrics."""

    requests_total: int = 0
    requests_per_minute: float = 0.0
    avg_response_time_ms: float = 0.0
    error_rate: float = 0.0
    pipeline_runs: int = 0
    avg_pipeline_duration_s: float = 0.0
    ai_requests: int = 0
    ai_avg_latency_ms: float = 0.0
    active_cases: int = 0
    total_evidence: int = 0
    uptime_seconds: float = 0.0
    memory_usage_mb: float = 0.0


@dataclass
class _RequestRecord:
    timestamp: float
    status: int
    duration_ms: float


@dataclass
class _PipelineRecord:
    timestamp: float
    duration_s: float
    artefact_count: int


@dataclass
class _AIRecord:
    timestamp: float
    duration_ms: float
    tokens_in: int
    tokens_out: int


class MetricsCollector:
    """Collects runtime metrics for the monitoring dashboard."""

    def __init__(self, max_records: int = 10_000) -> None:
        self._started_at = time.monotonic()
        self._lock = Lock()
        self._requests: deque[_RequestRecord] = deque(maxlen=max_records)
        self._pipeline_runs: deque[_PipelineRecord] = deque(maxlen=max_records)
        self._ai_requests: deque[_AIRecord] = deque(maxlen=max_records)

    def record_request(
        self, method: str, path: str, status: int, duration_ms: float
    ) -> None:
        with self._lock:
            self._requests.append(
                _RequestRecord(timestamp=time.time(), status=status, duration_ms=duration_ms)
            )

    def record_pipeline_execution(
        self, job_id: str, duration_s: float, artefact_count: int
    ) -> None:
        with self._lock:
            self._pipeline_runs.append(
                _PipelineRecord(
                    timestamp=time.time(),
                    duration_s=duration_s,
                    artefact_count=artefact_count,
                )
            )

    def record_ai_request(
        self, model: str, tokens_in: int, tokens_out: int, duration_ms: float
    ) -> None:
        with self._lock:
            self._ai_requests.append(
                _AIRecord(
                    timestamp=time.time(),
                    duration_ms=duration_ms,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                )
            )

    def get_metrics_summary(self, since_minutes: int = 60) -> MetricsSummary:
        cutoff = time.time() - (since_minutes * 60)

        with self._lock:
            recent_requests = [r for r in self._requests if r.timestamp >= cutoff]
            recent_pipelines = [r for r in self._pipeline_runs if r.timestamp >= cutoff]
            recent_ai = [r for r in self._ai_requests if r.timestamp >= cutoff]

        req_total = len(recent_requests)
        req_per_min = req_total / max(since_minutes, 1)
        avg_resp = (
            sum(r.duration_ms for r in recent_requests) / req_total if req_total else 0.0
        )
        errors = sum(1 for r in recent_requests if r.status >= 500)
        error_rate = errors / req_total if req_total else 0.0

        pipe_count = len(recent_pipelines)
        avg_pipe = (
            sum(r.duration_s for r in recent_pipelines) / pipe_count
            if pipe_count
            else 0.0
        )

        ai_count = len(recent_ai)
        avg_ai = (
            sum(r.duration_ms for r in recent_ai) / ai_count if ai_count else 0.0
        )

        memory_mb = 0.0
        try:
            import psutil  # type: ignore[import-untyped]

            memory_mb = round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2)
        except Exception:  # noqa: BLE001
            pass

        return MetricsSummary(
            requests_total=req_total,
            requests_per_minute=round(req_per_min, 2),
            avg_response_time_ms=round(avg_resp, 2),
            error_rate=round(error_rate, 4),
            pipeline_runs=pipe_count,
            avg_pipeline_duration_s=round(avg_pipe, 2),
            ai_requests=ai_count,
            ai_avg_latency_ms=round(avg_ai, 2),
            uptime_seconds=round(time.monotonic() - self._started_at, 2),
            memory_usage_mb=memory_mb,
        )
