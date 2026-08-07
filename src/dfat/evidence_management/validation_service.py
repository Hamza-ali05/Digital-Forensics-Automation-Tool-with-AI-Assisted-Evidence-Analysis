"""Evidence format, size, and MIME validation with status transitions."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from dfat.case_management.enums import EvidenceStatus
from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.validators import SUPPORTED_DISK_EXTENSIONS, SUPPORTED_MEMORY_EXTENSIONS
from dfat.database.repositories.evidence_status_repo import (
    EvidenceMetadataRepository,
    EvidenceStatusRepository,
)
from dfat.evidence_management.exceptions import EvidenceValidationError
from dfat.evidence_management.hash_service import MultiHashService
from dfat.evidence_management.mime_identifier import MIMEIdentifier
from dfat.evidence_management.models import (
    EvidenceMetadataRecord,
    EvidenceStatusChange,
)
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.settings import DFATSettings


class EvidenceValidationService:
    """Validate forensic evidence files and drive status transitions."""

    def __init__(
        self,
        mime_identifier: MIMEIdentifier,
        hash_service: MultiHashService,
        evidence_status_repo: EvidenceStatusRepository,
        audit_logger: ForensicAuditLogger,
        settings: DFATSettings,
        evidence_metadata_repo: Optional[EvidenceMetadataRepository] = None,
    ) -> None:
        """Initialise the validation service.

        Args:
            mime_identifier: MIME detection helper.
            hash_service: Multi-algorithm hash service.
            evidence_status_repo: Status history repository.
            audit_logger: Forensic audit logger.
            settings: Application settings (size limits, formats).
            evidence_metadata_repo: Optional metadata persistence repository.
        """
        self._mime = mime_identifier
        self._hash_service = hash_service
        self._status_repo = evidence_status_repo
        self._audit_logger = audit_logger
        self._settings = settings
        self._metadata_repo = evidence_metadata_repo

    async def validate_evidence(
        self,
        evidence_id: str,
        file_path: Path | str,
        declared_type: EvidenceType,
        user_id: str,
    ) -> EvidenceMetadataRecord:
        """Validate evidence and transition REGISTERED → VALIDATING → VALIDATED.

        On failure the status transitions to QUARANTINED and an
        ``EvidenceValidationError`` is raised (except existence failures, which
        quarantine and re-raise as ``EvidenceValidationError``).

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file (read-only).
            declared_type: Declared disk image or memory dump type.
            user_id: Acting user identifier.

        Returns:
            Populated ``EvidenceMetadataRecord``.
        """
        path = Path(file_path)
        failures: list[str] = []
        notes: list[str] = []

        await self._transition(
            evidence_id,
            previous=EvidenceStatus.REGISTERED,
            new=EvidenceStatus.VALIDATING,
            user_id=user_id,
            reason="Validation started",
        )

        try:
            if not path.exists() or not path.is_file():
                failures.append(f"Evidence file not found or not a file: {path}")
                await self._quarantine(evidence_id, user_id, failures)
                raise EvidenceValidationError(
                    "Evidence validation failed: file not found",
                    validation_failures=failures,
                    context={"evidence_id": evidence_id, "path": str(path)},
                )

            file_size = path.stat().st_size
            if file_size <= 0:
                failures.append("Evidence file is empty (zero bytes)")
            max_bytes = int(
                self._settings.evidence.max_evidence_size_gb * (1024**3)
            )
            if file_size > max_bytes:
                failures.append(
                    f"Evidence file exceeds max size "
                    f"({self._settings.evidence.max_evidence_size_gb} GB)"
                )

            mime_type, detection_method = self._mime.identify(path)
            extension = path.suffix.lower()
            notes.append(f"MIME detected via {detection_method}: {mime_type}")

            allowed = (
                SUPPORTED_DISK_EXTENSIONS
                if declared_type is EvidenceType.DISK_IMAGE
                else SUPPORTED_MEMORY_EXTENSIONS
            )
            # Prefer settings-backed formats when configured.
            settings_allowed = (
                self._settings.evidence.supported_disk_formats
                if declared_type is EvidenceType.DISK_IMAGE
                else self._settings.evidence.supported_memory_formats
            )
            if settings_allowed:
                allowed = {ext.lower() for ext in settings_allowed}

            if extension not in allowed:
                failures.append(
                    f"Unsupported extension {extension!r} for {declared_type.value}"
                )

            if not self._mime.is_forensic_image(
                mime_type,
                extension,
                evidence_type=declared_type,
            ):
                failures.append(
                    f"MIME/extension combination not accepted for forensic "
                    f"image: mime={mime_type}, ext={extension}"
                )

            if failures:
                await self._quarantine(evidence_id, user_id, failures)
                raise EvidenceValidationError(
                    "Evidence validation failed",
                    validation_failures=failures,
                    context={"evidence_id": evidence_id, "path": str(path)},
                )

            hash_set = self._hash_service.compute_hash_set(path, evidence_id)
            created_at, modified_at, accessed_at = self._extract_timestamps(path)

            metadata = EvidenceMetadataRecord(
                evidence_id=evidence_id,
                mime_type=mime_type,
                mime_detected_from=detection_method,
                file_extension=extension,
                file_size_bytes=file_size,
                file_created_at=created_at,
                file_modified_at=modified_at,
                file_accessed_at=accessed_at,
                hash_set=hash_set,
                is_valid_format=True,
                validation_notes=notes,
                extracted_at=datetime.now(UTC),
            )

            if self._metadata_repo is not None:
                await self._metadata_repo.save_metadata(metadata)

            await self._transition(
                evidence_id,
                previous=EvidenceStatus.VALIDATING,
                new=EvidenceStatus.VALIDATED,
                user_id=user_id,
                reason="Validation succeeded",
            )
            self._audit_logger.log_action(
                stage=PipelineStage.ACQUISITION,
                action="EVIDENCE_VALIDATED",
                evidence_id=evidence_id,
                hash_after=hash_set.sha256,
                details={
                    "path": str(path),
                    "mime_type": mime_type,
                    "mime_detected_from": detection_method,
                    "file_size_bytes": file_size,
                    "declared_type": declared_type.value,
                },
            )
            return metadata

        except EvidenceValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            failures.append(str(exc))
            await self._quarantine(evidence_id, user_id, failures)
            raise EvidenceValidationError(
                "Evidence validation failed with unexpected error",
                validation_failures=failures,
                context={"evidence_id": evidence_id, "path": str(path)},
            ) from exc

    async def revalidate_evidence(
        self,
        evidence_id: str,
        file_path: Path | str,
        declared_type: EvidenceType,
        user_id: str,
    ) -> EvidenceMetadataRecord:
        """Re-run validation from QUARANTINED via REGISTERED → VALIDATING → …

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file.
            declared_type: Declared evidence type.
            user_id: Acting user identifier.

        Returns:
            Fresh ``EvidenceMetadataRecord`` on success.
        """
        current = await self._status_repo.get_current_status(evidence_id)
        if current is EvidenceStatus.QUARANTINED:
            await self._transition(
                evidence_id,
                previous=EvidenceStatus.QUARANTINED,
                new=EvidenceStatus.REGISTERED,
                user_id=user_id,
                reason="Revalidation requested — cleared quarantine",
            )
        return await self.validate_evidence(
            evidence_id,
            file_path,
            declared_type,
            user_id,
        )

    async def _quarantine(
        self,
        evidence_id: str,
        user_id: str,
        failures: list[str],
    ) -> None:
        """Transition evidence to QUARANTINED and audit the failure."""
        current = await self._status_repo.get_current_status(evidence_id)
        if current is EvidenceStatus.QUARANTINED:
            return
        previous = current or EvidenceStatus.VALIDATING
        await self._transition(
            evidence_id,
            previous=previous,
            new=EvidenceStatus.QUARANTINED,
            user_id=user_id,
            reason="; ".join(failures)[:1000],
        )
        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="EVIDENCE_QUARANTINED",
            evidence_id=evidence_id,
            details={"validation_failures": failures},
        )

    async def _transition(
        self,
        evidence_id: str,
        *,
        previous: Optional[EvidenceStatus],
        new: EvidenceStatus,
        user_id: str,
        reason: str,
    ) -> None:
        """Record a status change via the status repository."""
        await self._status_repo.add_status_change(
            EvidenceStatusChange(
                evidence_id=evidence_id,
                previous_status=previous,
                new_status=new,
                changed_by_user_id=user_id,
                changed_at=datetime.now(UTC),
                reason=reason,
            )
        )

    @staticmethod
    def _extract_timestamps(
        path: Path,
    ) -> tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
        """Extract created/modified/accessed timestamps from ``os.stat``."""
        try:
            stat_result = os.stat(path)
        except OSError:
            return None, None, None

        def _from_ts(value: float) -> Optional[datetime]:
            try:
                return datetime.fromtimestamp(value, tz=UTC)
            except (OverflowError, OSError, ValueError):
                return None

        # st_ctime is creation time on Windows; change time on Unix.
        created = _from_ts(getattr(stat_result, "st_birthtime", stat_result.st_ctime))
        modified = _from_ts(stat_result.st_mtime)
        accessed = _from_ts(stat_result.st_atime)
        return created, modified, accessed
