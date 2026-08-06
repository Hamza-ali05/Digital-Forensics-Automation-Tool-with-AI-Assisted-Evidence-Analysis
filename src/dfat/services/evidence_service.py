"""Evidence registration and integrity verification services."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.exceptions import EvidenceNotFoundError, UnsupportedFormatError
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.pipeline import AuditEntry
from dfat.core.validators import (
    SUPPORTED_DISK_EXTENSIONS,
    SUPPORTED_MEMORY_EXTENSIONS,
    validate_evidence_path,
    validate_file_extension,
)
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.forensic_engine.acquisition.image_handler import DiskImageHandler
from dfat.forensic_engine.acquisition.integrity import IntegrityChecker
from dfat.forensic_engine.acquisition.memory_handler import MemoryDumpHandler
from dfat.infrastructure.storage.local_storage import LocalFileStorage


class EvidenceService:
    """Business logic for evidence metadata registration and verification."""

    def __init__(
        self,
        evidence_repo: SQLAlchemyEvidenceRepository,
        integrity_checker: IntegrityChecker,
        disk_handler: DiskImageHandler,
        memory_handler: MemoryDumpHandler,
        audit_repo: SQLAlchemyAuditRepository,
        storage: LocalFileStorage,
    ) -> None:
        """Initialise the evidence service.

        Args:
            evidence_repo: Evidence metadata repository.
            integrity_checker: Hash verification service.
            disk_handler: Disk image acquisition handler.
            memory_handler: Memory dump acquisition handler.
            audit_repo: Database audit repository.
            storage: Local storage adapter (path utilities).
        """
        self._evidence_repo = evidence_repo
        self._integrity_checker = integrity_checker
        self._disk_handler = disk_handler
        self._memory_handler = memory_handler
        self._audit_repo = audit_repo
        self._storage = storage

    async def register_evidence(
        self,
        file_path: Path,
        case_name: str,
        investigator: str,
        evidence_type: EvidenceType,
        description: Optional[str],
        user_id: str,
    ) -> EvidenceImage:
        """Register evidence metadata after integrity hashing.

        Args:
            file_path: Path to evidence file on local disk.
            case_name: Case display name.
            investigator: Investigator name.
            evidence_type: Disk image or memory dump.
            description: Optional case description.
            user_id: Registering user ID.

        Returns:
            Persisted domain evidence model.
        """
        path = validate_evidence_path(Path(file_path))
        if evidence_type is EvidenceType.DISK_IMAGE:
            if not validate_file_extension(path, SUPPORTED_DISK_EXTENSIONS):
                raise UnsupportedFormatError(
                    f"Unsupported disk extension: {path.suffix}",
                    context={"path": str(path)},
                )
        elif not validate_file_extension(path, SUPPORTED_MEMORY_EXTENSIONS):
            raise UnsupportedFormatError(
                f"Unsupported memory extension: {path.suffix}",
                context={"path": str(path)},
            )

        case = CaseMetadata(
            case_name=case_name,
            investigator=investigator,
            description=description,
        )
        if evidence_type is EvidenceType.MEMORY_DUMP:
            evidence = await asyncio.to_thread(
                self._memory_handler.load_dump,
                path,
                case,
            )
        else:
            evidence = await asyncio.to_thread(
                self._disk_handler.load_image,
                path,
                case,
            )
        await self._evidence_repo.save(evidence)
        await self._audit(
            action="EVIDENCE_REGISTERED",
            evidence_id=evidence.evidence_id,
            user_id=user_id,
            details={
                "file_path": str(path),
                "evidence_type": evidence.evidence_type.value,
                "original_hash": evidence.original_hash,
                "storage_base": str(self._storage.base_dir),
            },
        )
        return evidence

    async def get_evidence(self, evidence_id: str) -> EvidenceImage:
        """Load evidence metadata by ID."""
        evidence = await self._evidence_repo.get(evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(
                f"Evidence not found: {evidence_id}",
                context={"evidence_id": evidence_id},
            )
        return evidence

    async def list_evidence(self) -> list[EvidenceImage]:
        """List all registered evidence metadata."""
        return await self._evidence_repo.list_all()

    async def verify_evidence_integrity(self, evidence_id: str) -> bool:
        """Recompute and verify the integrity hash for evidence."""
        evidence = await self.get_evidence(evidence_id)
        return await asyncio.to_thread(
            self._integrity_checker.verify_integrity,
            evidence.file_path,
            evidence.original_hash,
            evidence.evidence_id,
        )

    async def delete_evidence(self, evidence_id: str, user_id: str) -> bool:
        """Delete evidence metadata only (never deletes the original file)."""
        evidence = await self._evidence_repo.get(evidence_id)
        if evidence is None:
            return False
        deleted = await self._evidence_repo.delete(evidence_id)
        if deleted:
            await self._audit(
                action="EVIDENCE_METADATA_DELETED",
                evidence_id=evidence_id,
                user_id=user_id,
                details={
                    "file_path": str(evidence.file_path),
                    "note": "Original evidence file retained on disk",
                },
            )
        return deleted

    async def _audit(
        self,
        *,
        action: str,
        evidence_id: str,
        user_id: str,
        details: dict,
    ) -> None:
        """Append a database audit entry."""
        entry_number = await self._audit_repo.get_latest_entry_number() + 1
        entry = AuditEntry(
            entry_number=entry_number,
            stage=PipelineStage.ACQUISITION,
            action=action,
            evidence_id=evidence_id,
            details=details,
        )
        await self._audit_repo.log_entry(entry, user_id=user_id)
