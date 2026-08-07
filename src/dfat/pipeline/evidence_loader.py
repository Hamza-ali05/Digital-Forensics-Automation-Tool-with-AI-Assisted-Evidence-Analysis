"""Load forensic evidence into parser-ready handler contexts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.exceptions import EvidenceNotFoundError, UnsupportedFormatError
from dfat.core.models.evidence import EvidenceImage, MemoryDump
from dfat.evidence_management.hash_service import MultiHashService
from dfat.evidence_management.models import HashSet
from dfat.forensic_engine.acquisition.image_handler import DiskImageHandler
from dfat.forensic_engine.acquisition.integrity import IntegrityChecker
from dfat.forensic_engine.acquisition.memory_handler import MemoryDumpHandler
from dfat.services.audit_service import AuditService


class LoadedEvidence(BaseModel):
    """Evidence opened for pipeline parsing with live handler references.

    Attributes:
        evidence: Source evidence metadata.
        evidence_type: Disk image or memory dump classification.
        handler_context: Live handler objects for parsers.
            Disk: ``img_info``, ``fs_info``.
            Memory: ``volatility_context``.
        loaded_at: UTC timestamp when the evidence was loaded.
        integrity_verified: Whether integrity checks passed before open.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    evidence: EvidenceImage
    evidence_type: EvidenceType
    handler_context: dict[str, Any] = Field(default_factory=dict)
    loaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    integrity_verified: bool = False


class EvidenceLoader:
    """Prepare evidence for parser consumption with integrity verification."""

    def __init__(
        self,
        disk_handler: DiskImageHandler,
        memory_handler: MemoryDumpHandler,
        integrity_checker: IntegrityChecker,
        hash_service: MultiHashService,
        audit_service: AuditService,
    ) -> None:
        """Initialise the evidence loader.

        Args:
            disk_handler: Read-only disk image handler.
            memory_handler: Memory dump validation / Volatility context helper.
            integrity_checker: Single-algorithm integrity verifier.
            hash_service: Multi-algorithm hash service for ``HashSet`` checks.
            audit_service: Dual-write audit trail service.
        """
        self._disk_handler = disk_handler
        self._memory_handler = memory_handler
        self._integrity_checker = integrity_checker
        self._hash_service = hash_service
        self._audit = audit_service

    async def load_evidence(
        self,
        evidence: EvidenceImage,
        hash_set: Optional[HashSet] = None,
    ) -> LoadedEvidence:
        """Verify integrity and open evidence into a parser-ready context.

        Steps:
            1. Verify the evidence file exists.
            2. Verify integrity via ``HashSet`` when provided, otherwise
               single-hash SHA-256 (or configured algorithm) via
               ``IntegrityChecker``.
            3. Open disk or memory handler context by evidence type.
            4. Return ``LoadedEvidence`` with handler references.

        Args:
            evidence: Registered evidence metadata.
            hash_set: Optional multi-hash fingerprint; when present,
                ``verify_hash_set`` is used instead of single-hash verify.

        Returns:
            Loaded evidence with handler context.

        Raises:
            EvidenceNotFoundError: If the file path is missing or not a file.
            UnsupportedFormatError: If the evidence type is not supported.
            IntegrityVerificationError: If integrity verification fails.
        """
        path = Path(evidence.file_path)
        if not path.exists() or not path.is_file():
            raise EvidenceNotFoundError(
                f"Evidence file not found: {path}",
                context={
                    "path": str(path),
                    "evidence_id": evidence.evidence_id,
                },
            )

        integrity_verified = self._verify_integrity(evidence, hash_set)
        evidence_type = evidence.evidence_type
        handler_context = self._build_handler_context(evidence)

        loaded = LoadedEvidence(
            evidence=evidence,
            evidence_type=evidence_type,
            handler_context=handler_context,
            integrity_verified=integrity_verified,
        )
        await self._audit.log_action(
            stage=PipelineStage.ACQUISITION,
            action="EVIDENCE_LOADED_FOR_PIPELINE",
            evidence_id=evidence.evidence_id,
            user_id=None,
            details={
                "evidence_type": evidence_type.value,
                "path": str(path),
                "integrity_verified": integrity_verified,
                "hash_set_used": hash_set is not None,
                "handler_keys": sorted(handler_context.keys()),
            },
        )
        return loaded

    async def unload_evidence(self, loaded: LoadedEvidence) -> None:
        """Release handler resources associated with a loaded evidence item.

        Args:
            loaded: Previously loaded evidence context.
        """
        img_info = loaded.handler_context.get("img_info")
        if img_info is not None:
            self._disk_handler.close_image(img_info)
        loaded.handler_context.clear()
        await self._audit.log_action(
            stage=PipelineStage.ACQUISITION,
            action="EVIDENCE_UNLOADED_FROM_PIPELINE",
            evidence_id=loaded.evidence.evidence_id,
            details={
                "evidence_type": loaded.evidence_type.value,
            },
        )

    def _verify_integrity(
        self,
        evidence: EvidenceImage,
        hash_set: Optional[HashSet],
    ) -> bool:
        """Verify evidence integrity using HashSet or single-hash fallback."""
        path = Path(evidence.file_path)
        if hash_set is not None:
            return self._hash_service.verify_hash_set(
                path,
                hash_set,
                evidence.evidence_id,
            )
        return self._integrity_checker.verify_integrity(
            path,
            evidence.original_hash,
            evidence.evidence_id,
        )

    def _build_handler_context(self, evidence: EvidenceImage) -> dict[str, Any]:
        """Open disk or memory handlers and return the context mapping."""
        if evidence.evidence_type is EvidenceType.DISK_IMAGE:
            img_info = self._disk_handler.open_image(evidence)
            try:
                fs_info = self._disk_handler.get_filesystem(img_info)
            except Exception:
                self._disk_handler.close_image(img_info)
                raise
            return {"img_info": img_info, "fs_info": fs_info}

        if evidence.evidence_type is EvidenceType.MEMORY_DUMP:
            dump = self._as_memory_dump(evidence)
            if not self._memory_handler.validate_dump(dump):
                raise EvidenceNotFoundError(
                    f"Memory dump validation failed: {dump.file_path}",
                    context={
                        "path": str(dump.file_path),
                        "evidence_id": dump.evidence_id,
                    },
                )
            volatility_context = self._memory_handler.get_volatility_context(dump)
            return {"volatility_context": volatility_context}

        raise UnsupportedFormatError(
            f"Unsupported evidence type for pipeline load: {evidence.evidence_type}",
            context={
                "evidence_id": evidence.evidence_id,
                "evidence_type": evidence.evidence_type.value,
            },
        )

    @staticmethod
    def _as_memory_dump(evidence: EvidenceImage) -> MemoryDump:
        """Coerce ``EvidenceImage`` to ``MemoryDump`` when needed."""
        if isinstance(evidence, MemoryDump):
            return evidence
        return MemoryDump(**evidence.model_dump())
