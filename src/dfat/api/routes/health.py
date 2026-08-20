"""Health, readiness, and detailed system monitoring endpoints."""

from __future__ import annotations

import platform
import sys
import time
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import text

from dfat import __version__
from dfat.api.dependencies import require_role
from dfat.api.schemas.base import APIModel
from dfat.database.models.user import UserORM
from dfat.monitoring.health_aggregator import AggregatedHealth, HealthAggregator

router = APIRouter(prefix="/health", tags=["Health"])

_PROCESS_STARTED_AT = time.monotonic()

_TABLE_COUNT_QUERIES = {
    "users": text("SELECT COUNT(*) FROM users"),
    "roles": text("SELECT COUNT(*) FROM roles"),
    "evidence_records": text("SELECT COUNT(*) FROM evidence_records"),
    "artefact_records": text("SELECT COUNT(*) FROM artefact_records"),
    "report_records": text("SELECT COUNT(*) FROM report_records"),
    "audit_log": text("SELECT COUNT(*) FROM audit_log"),
}


class HealthResponse(APIModel):
    """Basic liveness response."""

    status: str = "healthy"
    version: str
    timestamp: datetime
    system_readiness: Optional[str] = None
    degraded_services: list[str] = Field(default_factory=list)
    available_capabilities: list[str] = Field(default_factory=list)


class ReadinessResponse(APIModel):
    """Readiness probe with component checks."""

    status: str
    checks: dict[str, bool]
    timestamp: datetime
    system_readiness: Optional[str] = None
    services: dict[str, str] = Field(default_factory=dict)


class DetailedHealthResponse(APIModel):
    """Admin-only detailed system information."""

    status: str
    version: str
    timestamp: datetime
    uptime_seconds: float
    python_version: str
    platform: str
    package_versions: dict[str, str] = Field(default_factory=dict)
    database_table_counts: dict[str, int] = Field(default_factory=dict)
    memory_usage_mb: Optional[float] = None
    checks: dict[str, bool] = Field(default_factory=dict)


def _container(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.container


def _startup_report(request: Request):
    """Return the bootstrap startup report stored on app state, if present."""
    return getattr(request.app.state, "startup_report", None)


def _system_readiness(request: Request) -> Optional[str]:
    """Return bootstrap system readiness from app state."""
    readiness = getattr(request.app.state, "system_readiness", None)
    if readiness is None:
        return None
    return readiness.value if hasattr(readiness, "value") else str(readiness)


def _service_status_map(request: Request) -> dict[str, str]:
    """Build per-phase service status from the startup report."""
    report = _startup_report(request)
    if report is None:
        return {}
    return {phase.phase.value: phase.status.value for phase in report.phases}


async def _aggregated_health(request: Request) -> AggregatedHealth:
    """Run the monitoring aggregator against the request DI container."""
    return await HealthAggregator.from_container(_container(request)).collect()


@router.get("", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Basic liveness check (no authentication)."""
    report = _startup_report(request)
    return HealthResponse(
        status="healthy",
        version=__version__,
        timestamp=datetime.now(UTC),
        system_readiness=_system_readiness(request),
        degraded_services=list(report.degraded_services) if report else [],
        available_capabilities=list(report.available_capabilities) if report else [],
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> ReadinessResponse:
    """Readiness check aggregating database, AI, storage, pipeline, and audit."""
    snapshot = await _aggregated_health(request)
    return ReadinessResponse(
        status=snapshot.readiness_status,
        checks=snapshot.checks,
        timestamp=datetime.now(UTC),
        system_readiness=_system_readiness(request),
        services=_service_status_map(request),
    )


@router.get("/detailed", response_model=DetailedHealthResponse)
async def detailed_health(
    request: Request,
    _: UserORM = Depends(require_role(["admin"])),
) -> DetailedHealthResponse:
    """Detailed system diagnostics (admin only)."""
    snapshot = await _aggregated_health(request)
    package_versions: dict[str, str] = {"dfat": __version__}
    for package_name in ("fastapi", "sqlalchemy", "pydantic", "uvicorn"):
        try:
            module = __import__(package_name)
            package_versions[package_name] = getattr(module, "__version__", "unknown")
        except Exception:  # noqa: BLE001
            package_versions[package_name] = "unavailable"

    table_counts: dict[str, int] = {}
    try:
        engine = _container(request).database.database_engine()
        async with engine.engine.connect() as connection:
            for table, query in _TABLE_COUNT_QUERIES.items():
                try:
                    result = await connection.execute(query)
                    table_counts[table] = int(result.scalar_one())
                except Exception:  # noqa: BLE001
                    table_counts[table] = -1
    except Exception:  # noqa: BLE001
        pass

    memory_mb: Optional[float] = None
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is kilobytes on Linux; bytes on macOS — approximate MB.
        memory_mb = round(usage.ru_maxrss / 1024.0, 2)
    except Exception:  # noqa: BLE001
        try:
            import psutil  # type: ignore[import-untyped]

            process = psutil.Process()
            memory_mb = round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception:  # noqa: BLE001
            memory_mb = None

    return DetailedHealthResponse(
        status=snapshot.readiness_status,
        version=__version__,
        timestamp=datetime.now(UTC),
        uptime_seconds=round(time.monotonic() - _PROCESS_STARTED_AT, 2),
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        package_versions=package_versions,
        database_table_counts=table_counts,
        memory_usage_mb=memory_mb,
        checks=snapshot.checks,
    )
