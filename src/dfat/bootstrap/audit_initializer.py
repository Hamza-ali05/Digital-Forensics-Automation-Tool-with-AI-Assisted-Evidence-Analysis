"""Forensic audit logging bootstrap and dual-write verification."""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from dfat import __version__
from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.core.enums import PipelineStage
from dfat.services.audit_service import AuditService
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)

_STARTUP_EVIDENCE_ID = "system"
_STARTUP_ACTION = "SYSTEM_STARTUP"
_DUAL_LOG_TEST_ACTION = "BOOTSTRAP_DUAL_LOG_TEST"


class AuditInitializer:
    """Verify audit log paths and dual-write forensic audit readiness."""

    def __init__(
        self,
        audit_service: AuditService,
        settings: DFATSettings,
    ) -> None:
        """Initialise the audit bootstrap helper.

        Args:
            audit_service: Dual-write audit trail service.
            settings: Application settings (paths, environment).
        """
        self._audit_service = audit_service
        self._settings = settings

    async def initialize(self) -> PhaseResult:
        """Verify audit storage and record a startup audit entry.

        Returns:
            ``PhaseResult`` with ``COMPLETED`` or ``FAILED``.
        """
        started = time.perf_counter()
        details: dict[str, Any] = {}

        audit_path = Path(self._settings.logging.audit_log_path)
        if not audit_path.is_absolute():
            audit_path = Path.cwd() / audit_path

        try:
            writable_ok = self._verify_audit_log_writable(audit_path)
            details["audit_log_writable"] = writable_ok
            if not writable_ok:
                return self._failed(
                    started,
                    f"Audit log path is not writable: {audit_path}. "
                    "Check permissions and DFAT_LOGGING__AUDIT_LOG_PATH.",
                    details,
                )

            db_ok = await self._verify_database_audit_accessible()
            details["database_audit_accessible"] = db_ok
            if not db_ok:
                return self._failed(
                    started,
                    "Database audit table is not accessible. "
                    "Run database initialization before audit bootstrap.",
                    details,
                )

            dual_ok = await self._verify_dual_logging()
            details["dual_logging_verified"] = dual_ok
            if not dual_ok:
                return self._failed(
                    started,
                    "Dual audit logging (file + database) verification failed.",
                    details,
                )

            await self._audit_service.log_action(
                stage=PipelineStage.ACQUISITION,
                action=_STARTUP_ACTION,
                evidence_id=_STARTUP_EVIDENCE_ID,
                details={
                    "environment": self._settings.env,
                    "version": __version__,
                    "event": "bootstrap_startup",
                },
            )
            startup_entries = await self._audit_service.get_audit_trail(
                _STARTUP_EVIDENCE_ID
            )
            startup_logged = any(
                entry.action == _STARTUP_ACTION for entry in startup_entries
            )
            details["startup_audit_logged"] = startup_logged
            if not startup_logged:
                return self._failed(
                    started,
                    "SYSTEM_STARTUP audit entry was not persisted to the database.",
                    details,
                )

            file_entries = self._audit_service._file_logger.get_audit_trail(  # noqa: SLF001
                _STARTUP_EVIDENCE_ID
            )
            file_startup = any(entry.action == _STARTUP_ACTION for entry in file_entries)
            details["startup_file_logged"] = file_startup
            if not file_startup:
                return self._failed(
                    started,
                    "SYSTEM_STARTUP audit entry was not persisted to the audit log file.",
                    details,
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Audit initialization failed")
            return self._failed(
                started,
                f"Audit initialization error: {exc}",
                details,
            )

        duration_ms = (time.perf_counter() - started) * 1000.0
        return PhaseResult(
            phase=InitPhase.AUDIT_LOGGING,
            status=InitStatus.COMPLETED,
            duration_ms=duration_ms,
            message="Forensic audit logging ready",
            details=details,
            is_critical=True,
        )

    def _verify_audit_log_writable(self, audit_path: Path) -> bool:
        """Write and delete a probe file beside the configured audit log path."""
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        probe_dir = audit_path.parent
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".dfat_audit_write_test_",
                dir=str(probe_dir),
                delete=False,
            ) as handle:
                handle.write("dfat bootstrap audit write probe\n")
                probe_path = Path(handle.name)
            probe_path.unlink(missing_ok=True)
            return True
        except OSError as exc:
            logger.error("Audit log write probe failed: %s", exc)
            return False

    async def _verify_database_audit_accessible(self) -> bool:
        """Return whether the audit repository responds to a read query."""
        try:
            await self._audit_service._audit_repo.get_latest_entry_number()  # noqa: SLF001
            return True
        except Exception:  # noqa: BLE001
            return False

    async def _verify_dual_logging(self) -> bool:
        """Log a probe entry and confirm it appears in file and database trails."""
        before_db = await self._audit_service._audit_repo.get_latest_entry_number()  # noqa: SLF001
        before_file_count = len(list(self._audit_service._file_logger._iter_records()))  # noqa: SLF001

        await self._audit_service.log_action(
            stage=PipelineStage.ACQUISITION,
            action=_DUAL_LOG_TEST_ACTION,
            evidence_id=_STARTUP_EVIDENCE_ID,
            details={"probe": True},
        )

        after_db = await self._audit_service._audit_repo.get_latest_entry_number()  # noqa: SLF001
        if after_db <= before_db:
            return False

        db_entries = await self._audit_service.get_audit_trail(_STARTUP_EVIDENCE_ID)
        if not any(entry.action == _DUAL_LOG_TEST_ACTION for entry in db_entries):
            return False

        after_file_count = len(list(self._audit_service._file_logger._iter_records()))  # noqa: SLF001
        if after_file_count <= before_file_count:
            return False

        file_entries = self._audit_service._file_logger.get_audit_trail(  # noqa: SLF001
            _STARTUP_EVIDENCE_ID
        )
        return any(entry.action == _DUAL_LOG_TEST_ACTION for entry in file_entries)

    def _failed(
        self,
        started: float,
        error: str,
        details: dict[str, Any],
    ) -> PhaseResult:
        """Build a FAILED audit phase result."""
        duration_ms = (time.perf_counter() - started) * 1000.0
        logger.error("Audit initialization failed: %s", error)
        return PhaseResult(
            phase=InitPhase.AUDIT_LOGGING,
            status=InitStatus.FAILED,
            duration_ms=duration_ms,
            message="Audit initialization failed — startup aborted",
            details=details,
            error=error,
            is_critical=True,
        )
