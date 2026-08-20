"""Continuous runtime health monitoring for core DFAT services."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from dfat.bootstrap.models import ServiceHealth, SystemReadiness

logger = logging.getLogger(__name__)

ServiceCheck = Callable[[], Awaitable[tuple[bool, dict[str, Any]]]]

_CRITICAL_SERVICES = frozenset({"database", "audit_logger"})
_HISTORY_MAX_ENTRIES = 500


class ServiceMonitor:
    """Continuously monitors service health at runtime."""

    MONITORED_SERVICES: tuple[str, ...] = (
        "database",
        "ollama",
        "vector_store",
        "filesystem",
        "audit_logger",
    )

    def __init__(
        self,
        db_engine: Any,
        llm_connection: Any,
        vector_store: Any,
        settings: Any,
        audit_logger: Any,
        check_interval_seconds: int = 30,
    ) -> None:
        self._check_interval_seconds = check_interval_seconds
        self._latest: dict[str, ServiceHealth] = {}
        self._history: dict[str, deque[ServiceHealth]] = defaultdict(
            lambda: deque(maxlen=_HISTORY_MAX_ENTRIES)
        )
        self._consecutive_failures: dict[str, int] = defaultdict(int)
        self._service_checks: dict[str, ServiceCheck] = {
            "database": self._database_check,
            "ollama": self._ollama_check,
            "vector_store": self._vector_store_check,
            "filesystem": self._filesystem_check,
            "audit_logger": self._audit_check,
        }
        self._db_engine = db_engine
        self._llm_connection = llm_connection
        self._vector_store = vector_store
        self._settings = settings
        self._audit_logger = audit_logger

    @property
    def check_interval_seconds(self) -> int:
        """Return the configured probe interval."""
        return self._check_interval_seconds

    async def check_all(self) -> dict[str, ServiceHealth]:
        """Run health probes for every monitored service."""
        results: dict[str, ServiceHealth] = {}
        for name in self.MONITORED_SERVICES:
            results[name] = await self.check_service(name)
        return results

    async def check_service(self, name: str) -> ServiceHealth:
        """Probe a single monitored service and record the result."""
        check = self._service_checks.get(name)
        if check is None:
            raise KeyError(f"Unknown monitored service: {name}")

        started = time.perf_counter()
        healthy = False
        details: dict[str, Any] = {}
        try:
            healthy, details = await check()
        except Exception as exc:  # noqa: BLE001
            details = {"error": str(exc)}
            logger.warning("Health check for %s failed: %s", name, exc)

        duration_ms = (time.perf_counter() - started) * 1000.0
        if healthy:
            self._consecutive_failures[name] = 0
        else:
            self._consecutive_failures[name] += 1

        snapshot = ServiceHealth(
            service_name=name,
            is_healthy=healthy,
            last_checked=datetime.now(UTC),
            response_time_ms=round(duration_ms, 2),
            details=details,
            consecutive_failures=self._consecutive_failures[name],
        )
        self._latest[name] = snapshot
        self._history[name].append(snapshot)
        return snapshot

    def get_overall_status(self) -> SystemReadiness:
        """Derive overall readiness from the latest probe results."""
        if not self._latest:
            return SystemReadiness.INITIALIZING

        if any(
            not self._latest[name].is_healthy
            for name in _CRITICAL_SERVICES
            if name in self._latest
        ):
            return SystemReadiness.UNAVAILABLE

        if any(not health.is_healthy for health in self._latest.values()):
            return SystemReadiness.DEGRADED

        return SystemReadiness.READY

    def get_health_history(
        self,
        service: str,
        minutes: int = 60,
    ) -> list[ServiceHealth]:
        """Return recent health snapshots for ``service`` within ``minutes``."""
        if service not in self._history:
            return []
        cutoff = datetime.now(UTC) - timedelta(minutes=max(minutes, 0))
        return [
            entry
            for entry in self._history[service]
            if entry.last_checked >= cutoff
        ]

    async def _database_check(self) -> tuple[bool, dict[str, Any]]:
        ok = bool(await self._db_engine.check_connection())
        return ok, {"connectivity": ok}

    async def _ollama_check(self) -> tuple[bool, dict[str, Any]]:
        health = await self._llm_connection.check_health()
        is_healthy = bool(getattr(health, "is_healthy", False))
        return is_healthy, {
            "model": getattr(health, "model_name", None),
            "response_time_ms": getattr(health, "response_time_ms", None),
            "error": getattr(health, "error", None),
        }

    async def _vector_store_check(self) -> tuple[bool, dict[str, Any]]:
        try:
            collections = await self._vector_store.list_collections()
            return True, {"collections": collections, "collection_count": len(collections)}
        except Exception as exc:  # noqa: BLE001
            return False, {"error": str(exc)}

    async def _filesystem_check(self) -> tuple[bool, dict[str, Any]]:
        evidence_dir = Path(self._settings.evidence.evidence_dir)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        probe = evidence_dir / ".dfat_health_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = evidence_dir.is_dir()
        return writable, {"evidence_dir": str(evidence_dir), "writable": writable}

    async def _audit_check(self) -> tuple[bool, dict[str, Any]]:
        audit_path = Path(getattr(self._audit_logger, "_audit_log_path", ""))
        if not audit_path:
            audit_path = Path(self._settings.logging.audit_log_path)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8"):
            pass
        return True, {"audit_log_path": str(audit_path)}
