"""Read-only disk image acquisition handler."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.exceptions import DiskParsingError, UnsupportedFormatError
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.validators import SUPPORTED_DISK_EXTENSIONS, validate_evidence_path
from dfat.forensic_engine.acquisition.integrity import IntegrityChecker
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.infrastructure.storage.local_storage import LocalFileStorage


class DiskImageHandler:
    """Acquire and open forensic disk images in read-only mode."""

    def __init__(
        self,
        integrity_checker: IntegrityChecker,
        audit_logger: ForensicAuditLogger,
        storage: LocalFileStorage,
    ) -> None:
        """Initialise the disk image handler.

        Args:
            integrity_checker: Integrity hashing and verification service.
            audit_logger: ACPO-compliant forensic audit logger.
            storage: Local storage adapter (path utilities / workspace).
        """
        self._integrity_checker = integrity_checker
        self._audit_logger = audit_logger
        self._storage = storage

    def load_image(self, image_path: Path, case: CaseMetadata) -> EvidenceImage:
        """Load a disk image, hash it, and return evidence metadata.

        Args:
            image_path: Path to the disk image file.
            case: Case metadata to associate with the evidence.

        Returns:
            Populated ``EvidenceImage`` model.

        Raises:
            EvidenceNotFoundError: If the path does not exist.
            UnsupportedFormatError: If the extension is not supported.
        """
        validated_path = validate_evidence_path(image_path)
        if validated_path.suffix.lower() not in {
            ext.lower() for ext in SUPPORTED_DISK_EXTENSIONS
        }:
            raise UnsupportedFormatError(
                f"Unsupported disk image format: {validated_path.suffix}",
                context={
                    "path": str(validated_path),
                    "allowed": sorted(SUPPORTED_DISK_EXTENSIONS),
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

        evidence = EvidenceImage(
            evidence_id=evidence_id,
            file_path=validated_path,
            evidence_type=EvidenceType.DISK_IMAGE,
            original_hash=digest,
            hash_algorithm=self._integrity_checker.hash_algorithm,
            file_size_bytes=validated_path.stat().st_size,
            acquired_at=datetime.now(UTC),
            case=case,
        )

        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="DISK_IMAGE_LOADED",
            evidence_id=evidence.evidence_id,
            hash_before=digest,
            hash_after=digest,
            details={
                "path": str(validated_path),
                "size_bytes": evidence.file_size_bytes,
                "storage_base": str(self._storage.base_dir),
            },
        )
        return evidence

    def open_image(self, evidence: EvidenceImage) -> Any:
        """Open a disk image with pytsk3 in read-only mode.

        Args:
            evidence: Previously loaded evidence metadata.

        Returns:
            ``pytsk3.Img_Info`` handle.

        Raises:
            ImportError: If ``pytsk3`` is not installed.
            DiskParsingError: If pytsk3 fails to open the image.
            IntegrityVerificationError: If integrity verification fails.
        """
        self._integrity_checker.verify_integrity(
            evidence.file_path,
            evidence.original_hash,
            evidence.evidence_id,
        )
        try:
            import pytsk3
        except ImportError as exc:
            raise ImportError(
                "pytsk3 is required for disk image analysis. Install with: "
                "pip install pytsk3"
            ) from exc

        try:
            img_info = pytsk3.Img_Info(str(evidence.file_path))
        except Exception as exc:  # noqa: BLE001 - bridge third-party errors
            raise DiskParsingError(
                f"Failed to open disk image: {evidence.file_path}",
                context={
                    "evidence_id": evidence.evidence_id,
                    "error": str(exc),
                },
            ) from exc

        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="DISK_IMAGE_OPENED",
            evidence_id=evidence.evidence_id,
            hash_before=evidence.original_hash,
            hash_after=evidence.original_hash,
            details={"path": str(evidence.file_path)},
        )
        return img_info

    def close_image(self, img_info: Any) -> None:
        """Release a previously opened disk image handle.

        Args:
            img_info: ``pytsk3.Img_Info`` handle (or compatible object).
        """
        close = getattr(img_info, "close", None)
        if callable(close):
            close()
        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="DISK_IMAGE_CLOSED",
            evidence_id="unknown",
            hash_before=None,
            hash_after=None,
            details={"handle_type": type(img_info).__name__},
        )

    def get_filesystem(self, img_info: Any, offset: int = 0) -> Any:
        """Open a filesystem view from an image handle.

        Args:
            img_info: Open ``pytsk3.Img_Info`` handle.
            offset: Partition offset in bytes.

        Returns:
            ``pytsk3.FS_Info`` filesystem handle.

        Raises:
            ImportError: If ``pytsk3`` is not installed.
            DiskParsingError: If filesystem opening fails.
        """
        try:
            import pytsk3
        except ImportError as exc:
            raise ImportError(
                "pytsk3 is required for disk image analysis. Install with: "
                "pip install pytsk3"
            ) from exc

        try:
            return pytsk3.FS_Info(img_info, offset=offset)
        except Exception as exc:  # noqa: BLE001 - bridge third-party errors
            raise DiskParsingError(
                f"Failed to open filesystem at offset {offset}",
                context={"offset": offset, "error": str(exc)},
            ) from exc
