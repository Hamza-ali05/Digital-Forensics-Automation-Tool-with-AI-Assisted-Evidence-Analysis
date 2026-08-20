"""Master boot sequencer coordinating all bootstrap initializers."""

from __future__ import annotations

import logging
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Optional

from dfat import __version__
from dfat.bootstrap.models import (
    InitPhase,
    InitStatus,
    PhaseResult,
    StartupReport,
    SystemReadiness,
)
from dfat.settings import DFATSettings
from dfat.shared.timing import PerformanceTimer

logger = logging.getLogger(__name__)

PhaseRunner = Callable[[], Awaitable[PhaseResult]]


class BootSequencer:
    """Orchestrates system startup in dependency order.

    Critical failures abort startup. Non-critical failures degrade gracefully.
    Produces a ``StartupReport`` documenting the state of every subsystem.
    """

    def __init__(
        self,
        settings: DFATSettings,
        config_validator: Any,
        directory_manager: Any,
        db_initializer: Any,
        auth_initializer: Any,
        audit_initializer: Any,
        parser_initializer: Any,
        dataset_initializer: Any,
        knowledge_initializer: Any,
        ai_initializer: Any,
        threat_intel_initializer: Any,
        reporting_initializer: Any,
        evaluation_initializer: Any,
        worker_initializer: Any,
    ) -> None:
        self._settings = settings
        self._config_validator = config_validator
        self._directory_manager = directory_manager
        self._db_initializer = db_initializer
        self._auth_initializer = auth_initializer
        self._audit_initializer = audit_initializer
        self._parser_initializer = parser_initializer
        self._dataset_initializer = dataset_initializer
        self._knowledge_initializer = knowledge_initializer
        self._ai_initializer = ai_initializer
        self._threat_intel_initializer = threat_intel_initializer
        self._reporting_initializer = reporting_initializer
        self._evaluation_initializer = evaluation_initializer
        self._worker_initializer = worker_initializer

    @property
    def BOOT_SEQUENCE(self) -> list[tuple[InitPhase, PhaseRunner, bool]]:
        """Ordered boot phases: ``(phase, runner, is_critical)``."""
        return [
            (InitPhase.CONFIGURATION, self._run_configuration, True),
            (InitPhase.DIRECTORIES, self._run_directories, True),
            (InitPhase.DATABASE, self._db_initializer.initialize, True),
            (InitPhase.AUTHENTICATION, self._auth_initializer.initialize, True),
            (InitPhase.AUDIT_LOGGING, self._audit_initializer.initialize, True),
            (InitPhase.FORENSIC_PARSERS, self._parser_initializer.initialize, False),
            (InitPhase.DATASET_DISCOVERY, self._dataset_initializer.initialize, False),
            (
                InitPhase.KNOWLEDGE_BASE,
                self._knowledge_initializer.initialize_knowledge_base,
                False,
            ),
            (
                InitPhase.IOC_DATABASE,
                self._knowledge_initializer.initialize_ioc,
                False,
            ),
            (
                InitPhase.THREAT_INTELLIGENCE,
                self._threat_intel_initializer.initialize,
                False,
            ),
            (InitPhase.ML_MODELS, self._ai_initializer.initialize_ml, False),
            (InitPhase.LLM_SERVICE, self._ai_initializer.initialize_llm, False),
            (InitPhase.RAG_PIPELINE, self._ai_initializer.initialize_rag, False),
            (InitPhase.REPORTING, self._reporting_initializer.initialize, True),
            (InitPhase.EVALUATION, self._evaluation_initializer.initialize, False),
            (
                InitPhase.BACKGROUND_WORKERS,
                self._worker_initializer.initialize,
                False,
            ),
        ]

    async def boot(self) -> StartupReport:
        """Run every initialization phase in dependency order.

        Returns:
            ``StartupReport`` — ``READY``, ``DEGRADED``, or ``UNAVAILABLE``.
        """
        started_at = datetime.now(UTC)
        phase_results: list[PhaseResult] = []

        logger.info("DFAT boot sequence starting (%d phases)", len(self.BOOT_SEQUENCE))

        for phase, runner, is_critical in self.BOOT_SEQUENCE:
            result = await self._run_phase(phase, runner, is_critical)
            phase_results.append(result)

            if result.status == InitStatus.FAILED and is_critical:
                logger.error(
                    "Critical phase %s failed — aborting startup: %s",
                    phase.value,
                    result.error or result.message,
                )
                return self._build_abort_report(phase_results, started_at)

        return self._build_success_report(phase_results, started_at)

    async def _run_phase(
        self,
        phase: InitPhase,
        runner: PhaseRunner,
        is_critical: bool,
    ) -> PhaseResult:
        """Execute one phase, capturing timing and unexpected exceptions."""
        logger.info("Boot phase starting: %s (critical=%s)", phase.value, is_critical)
        try:
            with PerformanceTimer() as timer:
                result = await runner()
            # Copy so later phases cannot mutate earlier report entries.
            result = result.model_copy(deep=True)
            result.phase = phase
            result.is_critical = is_critical
            if result.duration_ms <= 0:
                result.duration_ms = timer.elapsed_seconds * 1000.0
            logger.info(
                "Boot phase %s → %s (%.1fms)",
                phase.value,
                result.status.value,
                result.duration_ms,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("Boot phase %s raised unexpectedly", phase.value)
            return PhaseResult(
                phase=phase,
                status=InitStatus.FAILED,
                duration_ms=0.0,
                message=f"Phase {phase.value} raised an exception",
                details={},
                error=str(exc),
                is_critical=is_critical,
            )

    def _build_abort_report(
        self,
        results: list[PhaseResult],
        started_at: datetime,
    ) -> StartupReport:
        """Build an ``UNAVAILABLE`` report after a critical phase failure."""
        completed_at = datetime.now(UTC)
        failed = [
            r for r in results if r.status == InitStatus.FAILED and r.is_critical
        ]
        critical_failures = [
            f"{r.phase.value}: {r.error or r.message}" for r in failed
        ]
        return StartupReport(
            system_status=SystemReadiness.UNAVAILABLE,
            started_at=started_at,
            completed_at=completed_at,
            total_duration_ms=(completed_at - started_at).total_seconds() * 1000.0,
            phases=results,
            critical_failures=critical_failures,
            degraded_services=self._collect_degraded(results),
            available_capabilities=self._collect_capabilities(results),
            version=__version__,
            environment=str(self._settings.env),
            hostname=socket.gethostname(),
        )

    def _build_success_report(
        self,
        results: list[PhaseResult],
        started_at: datetime,
    ) -> StartupReport:
        """Build a ``READY`` or ``DEGRADED`` report after a full boot run."""
        completed_at = datetime.now(UTC)
        degraded = self._collect_degraded(results)
        failed_noncritical = [
            r.phase.value
            for r in results
            if r.status == InitStatus.FAILED and not r.is_critical
        ]
        system_status = (
            SystemReadiness.DEGRADED
            if degraded or failed_noncritical
            else SystemReadiness.READY
        )
        return StartupReport(
            system_status=system_status,
            started_at=started_at,
            completed_at=completed_at,
            total_duration_ms=(completed_at - started_at).total_seconds() * 1000.0,
            phases=results,
            critical_failures=[],
            degraded_services=degraded + failed_noncritical,
            available_capabilities=self._collect_capabilities(results),
            version=__version__,
            environment=str(self._settings.env),
            hostname=socket.gethostname(),
        )

    async def _run_configuration(self) -> PhaseResult:
        return await self._config_validator.validate(self._settings)

    async def _run_directories(self) -> PhaseResult:
        return await self._directory_manager.validate_and_create(self._settings)

    @staticmethod
    def _collect_degraded(results: list[PhaseResult]) -> list[str]:
        names: list[str] = []
        for result in results:
            if result.status == InitStatus.DEGRADED:
                names.append(result.phase.value)
            names.extend(result.degraded_capabilities)
        # Preserve order, drop duplicates.
        seen: set[str] = set()
        unique: list[str] = []
        for name in names:
            if name not in seen:
                seen.add(name)
                unique.append(name)
        return unique

    @staticmethod
    def _collect_capabilities(results: list[PhaseResult]) -> list[str]:
        return [
            r.phase.value
            for r in results
            if r.status in (InitStatus.COMPLETED, InitStatus.DEGRADED)
        ]
