"""Dual-write forensic audit trail service."""

from __future__ import annotations

from typing import Any, Optional

from dfat.core.enums import PipelineStage
from dfat.core.models.pipeline import AuditEntry
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger


class AuditService:
    """Coordinate database + file-based audit logging for forensic compliance."""

    def __init__(
        self,
        audit_repo: SQLAlchemyAuditRepository,
        forensic_audit_logger: ForensicAuditLogger,
    ) -> None:
        """Initialise the audit service.

        Args:
            audit_repo: Database audit repository (insert-only).
            forensic_audit_logger: File-based hash-chained audit logger.
        """
        self._audit_repo = audit_repo
        self._file_logger = forensic_audit_logger

    async def log_action(
        self,
        stage: PipelineStage,
        action: str,
        evidence_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log an action to both database and file audit trails.

        Args:
            stage: Pipeline stage associated with the action.
            action: Short action name.
            evidence_id: Optional evidence identifier.
            user_id: Optional acting user identifier.
            details: Optional structured details.
        """
        payload = dict(details or {})
        entry_number = await self._audit_repo.get_latest_entry_number() + 1
        entry = AuditEntry(
            entry_number=entry_number,
            stage=stage,
            action=action,
            evidence_id=evidence_id or "system",
            details=payload,
        )
        await self._audit_repo.log_entry(entry, user_id=user_id)
        self._file_logger.log_action(
            stage=stage,
            action=action,
            evidence_id=evidence_id or "system",
            details={**payload, "user_id": user_id},
        )

    async def flush(self) -> None:
        """Flush buffered forensic audit log writes to disk."""
        self._file_logger.flush()

    async def get_audit_trail(self, evidence_id: str) -> list[AuditEntry]:
        """Return database audit entries for an evidence ID."""
        return await self._audit_repo.get_by_evidence(evidence_id)

    async def get_user_audit_trail(self, user_id: str) -> list[AuditEntry]:
        """Return database audit entries for a user ID."""
        return await self._audit_repo.get_by_user(user_id)

    async def verify_trail_integrity(self, evidence_id: str) -> bool:
        """Verify file audit-chain integrity and sequential DB entry numbers.

        Args:
            evidence_id: Evidence identifier (used for DB trail checks).

        Returns:
            ``True`` when both file and DB trails look consistent.
        """
        file_ok = self._file_logger.verify_audit_integrity()
        entries = await self._audit_repo.get_by_evidence(evidence_id)
        if not entries:
            return file_ok
        numbers = [entry.entry_number for entry in entries]
        sequential = numbers == sorted(numbers)
        return file_ok and sequential
