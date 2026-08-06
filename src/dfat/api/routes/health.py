"""Health, readiness, and detailed system monitoring endpoints."""

from __future__ import annotations

import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from dfat import __version__
from dfat.api.dependencies import require_role
from dfat.database.models.user import UserORM

router = APIRouter(prefix="/health", tags=["Health"])

_PROCESS_STARTED_AT = time.monotonic()
_PROCESS_STARTED_WALL = datetime.now(UTC)


class HealthResponse(BaseModel):
    """Basic liveness response."""

    status: str = "healthy"
    version: str
    timestamp: datetime


class ReadinessResponse(BaseModel):
    """Readiness probe with component checks."""

    status: str
    checks: dict[str, bool]
    timestamp: datetime


class DetailedHealthResponse(BaseModel):
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


async def _check_database(request: Request) -> bool:
    """Return whether the database accepts a simple query."""
    try:
        engine = _container(request).database.database_engine()
        return await engine.check_connection()
    except Exception:  # noqa: BLE001
        return False


def _check_llm(request: Request) -> bool:
    """Return whether the local LLM client reports availability (optional)."""
    try:
        client = _container(request).ai_engine.llm_client()
        return bool(client.is_available())
    except Exception:  # noqa: BLE001
        return False


def _check_storage(request: Request) -> bool:
    """Return whether the configured evidence directory is accessible."""
    try:
        settings = _container(request).settings()
        evidence_dir = Path(settings.evidence.evidence_dir)
        if not evidence_dir.exists():
            evidence_dir.mkdir(parents=True, exist_ok=True)
        return evidence_dir.is_dir() and evidence_dir.exists()
    except Exception:  # noqa: BLE001
        return False


def _readiness_status(checks: dict[str, bool]) -> str:
    """Derive overall readiness from component checks."""
    if checks.get("database") and checks.get("storage"):
        if checks.get("llm"):
            return "ready"
        return "degraded"
    return "unavailable"


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Basic liveness check (no authentication)."""
    return HealthResponse(
        status="healthy",
        version=__version__,
        timestamp=datetime.now(UTC),
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> ReadinessResponse:
    """Readiness check for database, optional LLM, and evidence storage."""
    checks = {
        "database": await _check_database(request),
        "llm": _check_llm(request),
        "storage": _check_storage(request),
    }
    return ReadinessResponse(
        status=_readiness_status(checks),
        checks=checks,
        timestamp=datetime.now(UTC),
    )


@router.get("/detailed", response_model=DetailedHealthResponse)
async def detailed_health(
    request: Request,
    _: UserORM = Depends(require_role(["admin"])),
) -> DetailedHealthResponse:
    """Detailed system diagnostics (admin only)."""
    checks = {
        "database": await _check_database(request),
        "llm": _check_llm(request),
        "storage": _check_storage(request),
    }
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
            for table in (
                "users",
                "roles",
                "evidence_records",
                "artefact_records",
                "report_records",
                "audit_log",
            ):
                try:
                    result = await connection.execute(
                        text(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                    )
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
        status=_readiness_status(checks),
        version=__version__,
        timestamp=datetime.now(UTC),
        uptime_seconds=round(time.monotonic() - _PROCESS_STARTED_AT, 2),
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        package_versions=package_versions,
        database_table_counts=table_counts,
        memory_usage_mb=memory_mb,
        checks=checks,
    )
