"""Aggregate infrastructure health checks into a single system status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dfat.pipeline.enums import JobStatus

_IN_FLIGHT_STATUSES = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.INITIALISING,
        JobStatus.RUNNING,
        JobStatus.STAGE_COMPLETE,
    }
)

_HTTP_STATUS = {
    "healthy": "ready",
    "degraded": "degraded",
    "unhealthy": "unavailable",
}

# Required checks fail the system; optional checks only degrade it.
REQUIRED_CHECKS = ("database", "storage", "audit")
OPTIONAL_CHECKS = ("llm", "pipeline")


@dataclass(frozen=True)
class AggregatedHealth:
    """Combined health snapshot for readiness probes.

    Attributes:
        status: Overall status: ``healthy``, ``degraded``, or ``unhealthy``.
        checks: Named component results keyed for the HTTP readiness payload.
    """

    status: str
    checks: dict[str, bool]

    @property
    def readiness_status(self) -> str:
        """Map aggregator status onto the ``/health/ready`` contract."""
        return _HTTP_STATUS.get(self.status, "unavailable")


class HealthAggregator:
    """Combine health checks from core infrastructure components.

    Checks:
        database — SQL engine accepts ``SELECT 1``.
        llm / AI engine — local LLM client reports availability.
        storage / filesystem — evidence directory exists and is writable.
        pipeline — no in-flight jobs older than the stuck-job threshold.
        audit — forensic audit log path is writable.

    Overall status:
        ``unhealthy`` if any required check fails (database, filesystem, audit).
        ``degraded`` if only optional checks fail (LLM, stuck pipeline).
        ``healthy`` when every check succeeds.

    Used by the ``/health/ready`` endpoint.
    """

    STUCK_JOB_THRESHOLD = timedelta(hours=1)

    def __init__(
        self,
        container: Any,
        *,
        stuck_job_threshold: timedelta | None = None,
    ) -> None:
        """Initialise the aggregator over an application DI container.

        Args:
            container: Root ``ApplicationContainer`` (or compatible duck type).
            stuck_job_threshold: Age after which an in-flight job is stuck.
        """
        self._container = container
        self._stuck_job_threshold = stuck_job_threshold or self.STUCK_JOB_THRESHOLD

    @classmethod
    def from_container(cls, container: Any) -> HealthAggregator:
        """Build an aggregator bound to ``container``."""
        return cls(container)

    async def collect(self) -> AggregatedHealth:
        """Run all component checks and return the aggregated snapshot."""
        checks = {
            "database": await self.check_database(),
            "llm": self.check_ai_engine(),
            "storage": self.check_filesystem(),
            "pipeline": await self.check_pipeline(),
            "audit": self.check_audit_logger(),
        }
        return AggregatedHealth(status=self.overall_status(checks), checks=checks)

    @staticmethod
    def overall_status(checks: dict[str, bool]) -> str:
        """Derive ``healthy`` / ``degraded`` / ``unhealthy`` from named checks."""
        if any(not checks.get(name, False) for name in REQUIRED_CHECKS):
            return "unhealthy"
        if any(not checks.get(name, False) for name in OPTIONAL_CHECKS):
            return "degraded"
        return "healthy"

    async def check_database(self) -> bool:
        """Return whether the database accepts a connectivity probe."""
        try:
            engine = self._container.database.database_engine()
            return bool(await engine.check_connection())
        except Exception:  # noqa: BLE001 — health probes must never raise
            return False

    def check_ai_engine(self) -> bool:
        """Return whether the local LLM client reports availability."""
        try:
            client = self._container.ai_engine.llm_client()
            return bool(client.is_available())
        except Exception:  # noqa: BLE001
            return False

    def check_filesystem(self) -> bool:
        """Return whether the configured evidence directory is usable."""
        try:
            settings = self._container.settings()
            evidence_dir = Path(settings.evidence.evidence_dir)
            if not evidence_dir.exists():
                evidence_dir.mkdir(parents=True, exist_ok=True)
            return evidence_dir.is_dir()
        except Exception:  # noqa: BLE001
            return False

    async def check_pipeline(self) -> bool:
        """Return whether no in-flight jobs exceed the stuck-job threshold."""
        try:
            orchestrator = self._container.pipeline.pipeline_orchestrator()
            jobs = await orchestrator.list_pipeline_jobs()
            now = datetime.now(UTC)
            for job in jobs:
                status = getattr(job, "status", None)
                if status not in _IN_FLIGHT_STATUSES:
                    continue
                started = getattr(job, "started_at", None) or getattr(
                    job, "created_at", None
                )
                if started is None:
                    continue
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                if now - started > self._stuck_job_threshold:
                    return False
            return True
        except Exception:  # noqa: BLE001
            return False

    def check_audit_logger(self) -> bool:
        """Return whether the forensic audit log path is writable."""
        try:
            audit_logger = self._container.logging.forensic_audit_logger()
            path = Path(getattr(audit_logger, "_audit_log_path"))
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8"):
                pass
            return True
        except Exception:  # noqa: BLE001
            return False
