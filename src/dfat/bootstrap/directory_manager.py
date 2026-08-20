"""Filesystem directory verification and creation for bootstrap."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.core.enums import PipelineStage
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class DirectoryManager:
    """Verify and create the DFAT runtime directory tree.

    Critical failure only when a required directory cannot be created or
    is not writable.
    """

    REQUIRED_DIRECTORIES: list[tuple[str, str]] = [
        ("data/evidence", "Forensic evidence storage"),
        ("data/datasets", "Forensic and benchmark datasets"),
        ("data/outputs", "Pipeline output and reports"),
        ("data/outputs/reports", "Generated reports"),
        ("data/knowledge", "Knowledge base storage"),
        ("data/knowledge/vector_store", "ChromaDB vector database"),
        ("data/knowledge/graph", "Knowledge graph"),
        ("data/knowledge/ioc_db", "IOC database"),
        ("data/ml", "Machine learning workspace"),
        ("data/ml/models", "Trained model storage"),
        ("data/ml/experiments", "Experiment tracking"),
        ("data/questionnaire", "Usability questionnaire data"),
    ]

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        audit_logger: Optional[ForensicAuditLogger] = None,
    ) -> None:
        """Initialise the directory manager.

        Args:
            base_dir: Root for relative required paths (defaults to project root).
            audit_logger: Optional forensic audit logger for create events.
        """
        self._base_dir = Path(base_dir) if base_dir is not None else _PROJECT_ROOT
        self._audit_logger = audit_logger

    async def validate_and_create(self, settings: DFATSettings) -> PhaseResult:
        """Ensure every required directory exists and is writable.

        Existing directories are left unchanged aside from a writability probe.
        Missing directories are created and audited.

        Args:
            settings: Application settings (used for audit log path when needed).

        Returns:
            ``PhaseResult`` for the DIRECTORIES phase.
        """
        started = time.perf_counter()
        created: list[str] = []
        verified: list[str] = []
        failures: list[str] = []

        audit = self._audit_logger
        if audit is None:
            audit_path = Path(settings.logging.audit_log_path)
            if not audit_path.is_absolute():
                audit_path = self._base_dir / audit_path
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit = ForensicAuditLogger(audit_log_path=audit_path)

        for relative, purpose in self.REQUIRED_DIRECTORIES:
            target = (self._base_dir / relative).resolve()
            try:
                existed = target.exists()
                if not existed:
                    target.mkdir(parents=True, exist_ok=True)
                    created.append(str(target))
                    logger.info("Created directory %s (%s)", target, purpose)
                    audit.log_action(
                        stage=PipelineStage.ACQUISITION,
                        action="directory_created",
                        evidence_id="system",
                        details={
                            "path": str(target),
                            "purpose": purpose,
                            "relative": relative,
                        },
                    )
                if not target.is_dir():
                    failures.append(
                        f"{target} exists but is not a directory ({purpose}). "
                        "Remove the conflicting path and restart."
                    )
                    continue
                if not self._is_writable(target):
                    failures.append(
                        f"{target} is not writable ({purpose}). "
                        "Check filesystem permissions for the DFAT process user."
                    )
                    continue
                verified.append(str(target))
                if existed:
                    logger.debug("Verified existing directory %s (%s)", target, purpose)
            except OSError as exc:
                failures.append(
                    f"Unable to create or access {target} ({purpose}): {exc}. "
                    "Ensure the parent volume is mounted and writable."
                )

        duration_ms = (time.perf_counter() - started) * 1000.0
        details = {
            "base_dir": str(self._base_dir),
            "created": created,
            "verified": verified,
            "required_count": len(self.REQUIRED_DIRECTORIES),
        }

        if failures:
            return PhaseResult(
                phase=InitPhase.DIRECTORIES,
                status=InitStatus.FAILED,
                duration_ms=duration_ms,
                message="Directory validation failed — cannot proceed",
                details=details,
                error="; ".join(failures),
                is_critical=True,
            )

        message = (
            f"Directories ready ({len(verified)} verified"
            + (f", {len(created)} created" if created else ", none created")
            + ")"
        )
        return PhaseResult(
            phase=InitPhase.DIRECTORIES,
            status=InitStatus.COMPLETED,
            duration_ms=duration_ms,
            message=message,
            details=details,
            is_critical=True,
        )

    @staticmethod
    def _is_writable(directory: Path) -> bool:
        """Return whether ``directory`` allows creating and removing a temp file."""
        if not os.access(directory, os.W_OK):
            return False
        try:
            fd, probe = tempfile.mkstemp(prefix=".dfat_write_probe_", dir=str(directory))
            os.close(fd)
            Path(probe).unlink(missing_ok=True)
            return True
        except OSError:
            return False
