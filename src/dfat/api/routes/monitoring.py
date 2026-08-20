"""Production monitoring endpoints: metrics, logs, and uptime."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from dfat import __version__
from dfat.api.dependencies import require_role
from dfat.api.schemas.base import APIModel
from dfat.database.models.user import UserORM
from dfat.monitoring.metrics_collector import MetricsSummary

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])

_PROCESS_STARTED_AT = time.monotonic()


class UptimeResponse(APIModel):
    """Public uptime and version information."""

    status: str = "running"
    version: str
    uptime_seconds: float
    started_at: datetime


_BOOT_TIME = datetime.now(UTC)


class LogEntry(APIModel):
    """A single log entry returned from the logs endpoint."""

    timestamp: str
    level: str
    message: str


class LogsResponse(APIModel):
    """Paginated log entries response."""

    entries: list[LogEntry]
    total: int


@router.get("/uptime", response_model=UptimeResponse)
async def uptime() -> UptimeResponse:
    """Public uptime and version (no auth required)."""
    return UptimeResponse(
        version=__version__,
        uptime_seconds=round(time.monotonic() - _PROCESS_STARTED_AT, 2),
        started_at=_BOOT_TIME,
    )


@router.get("/metrics", response_model=MetricsSummary)
async def metrics(
    request: Request,
    since_minutes: int = Query(60, ge=1, le=1440),
    _: UserORM = Depends(require_role(["admin"])),
) -> MetricsSummary:
    """Runtime metrics summary (admin only)."""
    container = request.app.state.container
    collector = container.metrics_collector()
    return collector.get_metrics_summary(since_minutes=since_minutes)


@router.get("/logs", response_model=LogsResponse)
async def logs(
    request: Request,
    level: str = Query("WARNING", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    limit: int = Query(100, ge=1, le=1000),
    _: UserORM = Depends(require_role(["admin"])),
) -> LogsResponse:
    """Recent log entries filtered by level (admin only)."""
    container = request.app.state.container
    settings = container.settings()
    audit_log_path = Path(settings.logging.audit_log_path)

    level_priority = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_priority = level_priority.get(level.upper(), 2)

    entries: list[LogEntry] = []
    if audit_log_path.exists():
        import json

        try:
            lines = audit_log_path.read_text(encoding="utf-8").strip().splitlines()
            for line in reversed(lines):
                if len(entries) >= limit:
                    break
                try:
                    record = json.loads(line)
                    record_level = record.get("level", record.get("levelname", "INFO"))
                    if level_priority.get(record_level, 0) >= min_priority:
                        entries.append(
                            LogEntry(
                                timestamp=record.get("timestamp", ""),
                                level=record_level,
                                message=record.get("message", record.get("event", "")),
                            )
                        )
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError:
            pass

    return LogsResponse(entries=entries, total=len(entries))
