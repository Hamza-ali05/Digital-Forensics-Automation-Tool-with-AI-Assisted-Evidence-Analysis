"""Read-only memory dump acquisition handler."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.exceptions import UnsupportedFormatError
from dfat.core.models.evidence import CaseMetadata, MemoryDump
from dfat.core.validators import (
    SUPPORTED_MEMORY_EXTENSIONS,
    validate_evidence_path,
)
from dfat.forensic_engine.acquisition.integrity import IntegrityChecker
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.infrastructure.storage.local_storage import LocalFileStorage


class MemoryDumpHandler:
    """Acquire and validate forensic memory dumps for later Volatility parsing."""

    def __init__(
        self,
        integrity_checker: IntegrityChecker,
        audit_logger: ForensicAuditLogger,
        storage: LocalFileStorage,
        volatility_symbols_path: Optional[Path] = None,
    ) -> None:
        """Initialise the memory dump handler.

        Args:
            integrity_checker: Integrity hashing and verification service.
            audit_logger: ACPO-compliant forensic audit logger.
            storage: Local storage adapter (path utilities / workspace).
            volatility_symbols_path: Optional Volatility3 symbols directory.
        """
        self._integrity_checker = integrity_checker
        self._audit_logger = audit_logger
        self._storage = storage
        self._volatility_symbols_path = volatility_symbols_path

    def load_dump(
        self,
        dump_path: Path,
        case: CaseMetadata,
        volatility_profile: Optional[str] = None,
    ) -> MemoryDump:
        """Load a memory dump, hash it, and return evidence metadata.

        Args:
            dump_path: Path to the memory dump file.
            case: Case metadata to associate with the evidence.
            volatility_profile: Optional Volatility profile name.

        Returns:
            Populated ``MemoryDump`` model.

        Raises:
            EvidenceNotFoundError: If the path does not exist.
            UnsupportedFormatError: If the extension is not supported.
        """
        validated_path = validate_evidence_path(dump_path)
        if validated_path.suffix.lower() not in {
            ext.lower() for ext in SUPPORTED_MEMORY_EXTENSIONS
        }:
            raise UnsupportedFormatError(
                f"Unsupported memory dump format: {validated_path.suffix}",
                context={
                    "path": str(validated_path),
                    "allowed": sorted(SUPPORTED_MEMORY_EXTENSIONS),
                },
            )

        evidence_id = str(uuid4())
        digest = self._integrity_checker.compute_initial_hash(
            validated_path,
            evidence_id,
        )
        self._integrity_checker.verify_integrity(
            validated_path,
            digest,
            evidence_id,
        )

        evidence = MemoryDump(
            evidence_id=evidence_id,
            file_path=validated_path,
            evidence_type=EvidenceType.MEMORY_DUMP,
            original_hash=digest,
            hash_algorithm=self._integrity_checker.hash_algorithm,
            file_size_bytes=validated_path.stat().st_size,
            acquired_at=datetime.now(UTC),
            case=case,
            volatility_profile=volatility_profile,
            capture_timestamp=None,
        )

        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="MEMORY_DUMP_LOADED",
            evidence_id=evidence.evidence_id,
            hash_before=digest,
            hash_after=digest,
            details={
                "path": str(validated_path),
                "size_bytes": evidence.file_size_bytes,
                "volatility_profile": volatility_profile,
                "storage_base": str(self._storage.base_dir),
            },
        )
        return evidence

    def validate_dump(self, evidence: MemoryDump) -> bool:
        """Validate that a memory dump remains accessible and non-empty.

        Args:
            evidence: Memory dump metadata to validate.

        Returns:
            True if the dump path exists, has a supported extension, and size > 0.
        """
        path = evidence.file_path
        valid = (
            path.exists()
            and path.is_file()
            and path.stat().st_size > 0
            and path.suffix.lower()
            in {ext.lower() for ext in SUPPORTED_MEMORY_EXTENSIONS}
        )
        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="MEMORY_DUMP_VALIDATED",
            evidence_id=evidence.evidence_id,
            hash_before=evidence.original_hash,
            hash_after=evidence.original_hash,
            details={"valid": valid, "path": str(path)},
        )
        return valid

    def get_volatility_context(self, evidence: MemoryDump) -> dict[str, Any]:
        """Build a Volatility3 configuration dictionary for later parsing.

        Args:
            evidence: Memory dump metadata.

        Returns:
            Configuration mapping consumed by Volatility-based parsers.
        """
        symbols_path = (
            str(self._volatility_symbols_path)
            if self._volatility_symbols_path is not None
            else None
        )
        context = {
            "file_path": str(evidence.file_path),
            "profile": evidence.volatility_profile,
            "symbols_path": symbols_path,
        }
        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="VOLATILITY_CONTEXT_PREPARED",
            evidence_id=evidence.evidence_id,
            hash_before=evidence.original_hash,
            hash_after=evidence.original_hash,
            details=context,
        )
        return context
