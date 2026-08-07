"""Multi-algorithm cryptographic hashing for defence-in-depth integrity."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from dfat.core.enums import HashAlgorithm, PipelineStage
from dfat.core.exceptions import (
    EvidenceError,
    EvidenceNotFoundError,
    IntegrityVerificationError,
)
from dfat.evidence_management.models import HashSet
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.hashing import compute_file_hash, verify_hash


class MultiHashService:
    """Compute and verify MD5 + SHA-1 + SHA-256 in a single file pass.

    Evidence files are opened read-only. Digests are never written back to the
    evidence file. Coexists with ``shared.hashing`` single-algorithm helpers.
    """

    def __init__(
        self,
        audit_logger: ForensicAuditLogger,
        chunk_size: int = 65536,
    ) -> None:
        """Initialise the multi-hash service.

        Args:
            audit_logger: Forensic audit logger for integrity events.
            chunk_size: Read buffer size in bytes (default 64 KiB).
        """
        self._audit_logger = audit_logger
        self._chunk_size = chunk_size

    def compute_hash_set(self, file_path: Path, evidence_id: str) -> HashSet:
        """Compute MD5, SHA-1, and SHA-256 in a single sequential file pass.

        Args:
            file_path: Path to the evidence file (read-only).
            evidence_id: Evidence identifier for audit correlation.

        Returns:
            ``HashSet`` containing all three hex digests and file size.

        Raises:
            EvidenceNotFoundError: If the file does not exist.
            EvidenceError: If the file cannot be read due to permissions.
        """
        return self._compute(
            Path(file_path),
            evidence_id,
            progress_callback=None,
        )

    def compute_hash_set_with_progress(
        self,
        file_path: Path,
        evidence_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> HashSet:
        """Compute a hash set while reporting per-chunk progress.

        Args:
            file_path: Path to the evidence file (read-only).
            evidence_id: Evidence identifier for audit correlation.
            progress_callback: Optional ``(bytes_read, total_bytes)`` callback.

        Returns:
            ``HashSet`` containing all three hex digests and file size.
        """
        return self._compute(
            Path(file_path),
            evidence_id,
            progress_callback=progress_callback,
        )

    def verify_hash_set(
        self,
        file_path: Path,
        expected: HashSet,
        evidence_id: str,
    ) -> bool:
        """Recompute all three digests and compare against ``expected``.

        Args:
            file_path: Path to the evidence file (read-only).
            expected: Previously recorded hash set.
            evidence_id: Evidence identifier for audit correlation.

        Returns:
            ``True`` when MD5, SHA-1, and SHA-256 all match.

        Raises:
            IntegrityVerificationError: If any algorithm mismatches.
            EvidenceNotFoundError: If the file does not exist.
            EvidenceError: If the file cannot be read due to permissions.
        """
        path = Path(file_path)
        actual = self._compute(path, evidence_id, progress_callback=None, audit=False)

        mismatches: dict[str, dict[str, str]] = {}
        if actual.md5.lower() != expected.md5.lower():
            mismatches["md5"] = {
                "expected": expected.md5.lower(),
                "actual": actual.md5.lower(),
            }
        if actual.sha1.lower() != expected.sha1.lower():
            mismatches["sha1"] = {
                "expected": expected.sha1.lower(),
                "actual": actual.sha1.lower(),
            }
        if actual.sha256.lower() != expected.sha256.lower():
            mismatches["sha256"] = {
                "expected": expected.sha256.lower(),
                "actual": actual.sha256.lower(),
            }

        if mismatches:
            failed = ", ".join(sorted(mismatches.keys()))
            self._audit_logger.log_action(
                stage=PipelineStage.ACQUISITION,
                action="INTEGRITY_VIOLATION_DETECTED",
                evidence_id=evidence_id,
                hash_before=expected.sha256,
                hash_after=actual.sha256,
                details={
                    "path": str(path),
                    "failed_algorithms": list(mismatches.keys()),
                    "mismatches": mismatches,
                },
            )
            raise IntegrityVerificationError(
                f"Multi-hash integrity verification failed ({failed}) for {path}",
                expected_hash=expected.sha256.lower(),
                actual_hash=actual.sha256.lower(),
                context={
                    "path": str(path),
                    "evidence_id": evidence_id,
                    "failed_algorithms": list(mismatches.keys()),
                    "mismatches": mismatches,
                },
            )

        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="INTEGRITY_VERIFIED",
            evidence_id=evidence_id,
            hash_before=expected.sha256,
            hash_after=actual.sha256,
            details={
                "path": str(path),
                "algorithms": ["md5", "sha1", "sha256"],
                "file_size_bytes": actual.file_size_bytes,
            },
        )
        return True

    def verify_single_hash(
        self,
        file_path: Path,
        expected_hash: str,
        algorithm: HashAlgorithm,
        evidence_id: str,
    ) -> bool:
        """Verify a single-algorithm hash via ``shared.hashing``.

        Args:
            file_path: Path to the evidence file.
            expected_hash: Expected hexadecimal digest.
            algorithm: Hash algorithm to use.
            evidence_id: Evidence identifier for audit correlation.

        Returns:
            ``True`` when the digest matches.

        Raises:
            IntegrityVerificationError: If the digest does not match.
        """
        path = Path(file_path)
        try:
            verify_hash(path, expected_hash, algorithm)
        except IntegrityVerificationError as exc:
            self._audit_logger.log_action(
                stage=PipelineStage.ACQUISITION,
                action="INTEGRITY_VIOLATION_DETECTED",
                evidence_id=evidence_id,
                hash_before=expected_hash,
                hash_after=exc.actual_hash,
                details={
                    "path": str(path),
                    "algorithm": algorithm.value,
                    "mode": "single",
                },
            )
            raise

        actual = compute_file_hash(path, algorithm)
        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="INTEGRITY_VERIFIED",
            evidence_id=evidence_id,
            hash_before=expected_hash,
            hash_after=actual,
            details={
                "path": str(path),
                "algorithm": algorithm.value,
                "mode": "single",
            },
        )
        return True

    def _compute(
        self,
        file_path: Path,
        evidence_id: str,
        *,
        progress_callback: Optional[Callable[[int, int], None]],
        audit: bool = True,
    ) -> HashSet:
        """Single-pass multi-algorithm hash computation."""
        if not file_path.exists():
            raise EvidenceNotFoundError(
                f"Evidence file not found: {file_path}",
                context={"path": str(file_path), "evidence_id": evidence_id},
            )
        if not file_path.is_file():
            raise EvidenceNotFoundError(
                f"Evidence path is not a file: {file_path}",
                context={"path": str(file_path), "evidence_id": evidence_id},
            )

        md5 = hashlib.md5()  # noqa: S324 — forensic multi-hash defence-in-depth
        sha1 = hashlib.sha1()  # noqa: S324 — forensic multi-hash defence-in-depth
        sha256 = hashlib.sha256()
        bytes_read = 0

        try:
            total_bytes = file_path.stat().st_size
            with file_path.open("rb") as handle:
                while True:
                    chunk = handle.read(self._chunk_size)
                    if not chunk:
                        break
                    md5.update(chunk)
                    sha1.update(chunk)
                    sha256.update(chunk)
                    bytes_read += len(chunk)
                    if progress_callback is not None:
                        progress_callback(bytes_read, total_bytes)
        except FileNotFoundError as exc:
            raise EvidenceNotFoundError(
                f"Evidence file not found: {file_path}",
                context={"path": str(file_path), "evidence_id": evidence_id},
            ) from exc
        except PermissionError as exc:
            raise EvidenceError(
                f"Permission denied reading evidence file: {file_path}",
                context={"path": str(file_path), "evidence_id": evidence_id},
            ) from exc
        except OSError as exc:
            raise EvidenceError(
                f"Failed to read evidence file: {file_path}",
                context={
                    "path": str(file_path),
                    "evidence_id": evidence_id,
                    "error": str(exc),
                },
            ) from exc

        hash_set = HashSet(
            md5=md5.hexdigest(),
            sha1=sha1.hexdigest(),
            sha256=sha256.hexdigest(),
            computed_at=datetime.now(UTC),
            file_size_bytes=bytes_read,
        )

        if audit:
            self._audit_logger.log_action(
                stage=PipelineStage.ACQUISITION,
                action="MULTI_HASH_COMPUTED",
                evidence_id=evidence_id,
                hash_after=hash_set.sha256,
                details={
                    "path": str(file_path),
                    "md5": hash_set.md5,
                    "sha1": hash_set.sha1,
                    "sha256": hash_set.sha256,
                    "file_size_bytes": hash_set.file_size_bytes,
                    "chunk_size": self._chunk_size,
                },
            )
        return hash_set
