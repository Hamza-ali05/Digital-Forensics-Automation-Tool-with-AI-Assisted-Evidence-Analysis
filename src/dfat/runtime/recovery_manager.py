"""Automatic recovery strategies for failed runtime services."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dfat.bootstrap.models import SystemReadiness
from dfat.core.enums import PipelineStage
from dfat.services.audit_service import AuditService

logger = logging.getLogger(__name__)

_RECOVERY_THRESHOLD = 3
_CRITICAL_FAILURE_THRESHOLD = 10
_DATABASE_RETRY_ATTEMPTS = 3
_DATABASE_RETRY_BASE_DELAY_SECONDS = 0.5


class RecoveryManager:
    """Attempts automatic recovery when monitored services fail."""

    def __init__(
        self,
        service_monitor: Any,
        boot_sequencer: Any,
        audit_service: AuditService,
    ) -> None:
        self._service_monitor = service_monitor
        self._boot_sequencer = boot_sequencer
        self._audit_service = audit_service
        self._degraded_mode = False
        self._fallback_active: dict[str, bool] = {}

    @property
    def degraded_mode(self) -> bool:
        """Return whether the system has entered runtime degraded mode."""
        return self._degraded_mode

    def is_fallback_active(self, service_name: str) -> bool:
        """Return whether rule-based fallback is active for ``service_name``."""
        return self._fallback_active.get(service_name, False)

    async def attempt_recovery(self, service_name: str) -> bool:
        """Run a service-specific recovery strategy and re-probe health.

        Returns:
            ``True`` when the service probe succeeds after recovery.
        """
        await self._log_recovery(
            action="SERVICE_RECOVERY_ATTEMPT",
            service_name=service_name,
            details={"phase": "started"},
        )

        try:
            if service_name == "database":
                recovered = await self._recover_database()
            elif service_name == "ollama":
                recovered = await self._recover_ollama()
            elif service_name == "vector_store":
                recovered = await self._recover_vector_store()
            elif service_name == "filesystem":
                recovered = await self._recover_filesystem()
            else:
                logger.info("No automatic recovery strategy for service: %s", service_name)
                health = await self._service_monitor.check_service(service_name)
                recovered = health.is_healthy
        except Exception as exc:  # noqa: BLE001
            logger.exception("Recovery for %s raised unexpectedly", service_name)
            await self._log_recovery(
                action="SERVICE_RECOVERY_FAILED",
                service_name=service_name,
                details={"error": str(exc)},
            )
            return False

        health = await self._service_monitor.check_service(service_name)
        recovered = recovered and health.is_healthy

        await self._log_recovery(
            action="SERVICE_RECOVERY_COMPLETED" if recovered else "SERVICE_RECOVERY_FAILED",
            service_name=service_name,
            details={"recovered": recovered, "health": health.model_dump(mode="json")},
        )
        return recovered

    async def on_service_failure(
        self,
        service_name: str,
        consecutive_failures: int,
    ) -> None:
        """React to repeated probe failures without crashing the application."""
        try:
            if consecutive_failures > _CRITICAL_FAILURE_THRESHOLD:
                self._degraded_mode = True
                logger.critical(
                    "Service %s exceeded failure threshold (%d) — entering degraded mode",
                    service_name,
                    consecutive_failures,
                )
                await self._log_recovery(
                    action="SERVICE_FAILURE_CRITICAL",
                    service_name=service_name,
                    details={
                        "consecutive_failures": consecutive_failures,
                        "system_readiness": SystemReadiness.DEGRADED.value,
                    },
                )
                return

            if consecutive_failures > _RECOVERY_THRESHOLD:
                await self.attempt_recovery(service_name)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failure handler for %s did not complete: %s",
                service_name,
                exc,
            )

    async def _recover_database(self) -> bool:
        db_engine = self._service_monitor._db_engine
        for attempt in range(_DATABASE_RETRY_ATTEMPTS):
            if attempt:
                delay = _DATABASE_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                await asyncio.sleep(delay)
            try:
                if await db_engine.check_connection():
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Database recovery attempt %d/%d failed: %s",
                    attempt + 1,
                    _DATABASE_RETRY_ATTEMPTS,
                    exc,
                )
        return False

    async def _recover_ollama(self) -> bool:
        logger.warning("Ollama unavailable — activating rule-based fallback")
        self._fallback_active["ollama"] = True
        await self._log_recovery(
            action="LLM_FALLBACK_ACTIVATED",
            service_name="ollama",
            details={"fallback": "rule_based"},
        )
        return True

    async def _recover_vector_store(self) -> bool:
        vector_store = self._service_monitor._vector_store
        if hasattr(vector_store, "_client"):
            vector_store._client = None
        knowledge_initializer = getattr(self._boot_sequencer, "_knowledge_initializer", None)
        if knowledge_initializer is not None:
            await knowledge_initializer.initialize_knowledge_base()
        await vector_store.list_collections()
        return True

    async def _recover_filesystem(self) -> bool:
        health = await self._service_monitor.check_service("filesystem")
        return health.is_healthy

    async def _log_recovery(
        self,
        *,
        action: str,
        service_name: str,
        details: dict[str, Any],
    ) -> None:
        await self._audit_service.log_action(
            stage=PipelineStage.ACQUISITION,
            action=action,
            evidence_id="system",
            details={"service": service_name, **details},
        )
