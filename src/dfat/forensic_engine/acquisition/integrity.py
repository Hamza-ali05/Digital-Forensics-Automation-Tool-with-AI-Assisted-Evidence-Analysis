"""Hash-based integrity verification and chain-of-custody records."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from dfat.core.enums import HashAlgorithm, PipelineStage
from dfat.core.exceptions import IntegrityVerificationError
from dfat.core.models.evidence import EvidenceImage
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.hashing import compute_file_hash, verify_hash


class IntegrityChecker:
    """Compute and verify evidence integrity hashes with audit logging."""

    def __init__(
        self,
        audit_logger: ForensicAuditLogger,
        hash_algorithm: HashAlgorithm = HashAlgorithm.SHA256,
    ) -> None:
        """Initialise the integrity checker.

        Args:
            audit_logger: ACPO-compliant forensic audit logger.
            hash_algorithm: Hash algorithm used for integrity checks.
        """
        self._audit_logger = audit_logger
        self._hash_algorithm = hash_algorithm

    @property
    def hash_algorithm(self) -> HashAlgorithm:
        """Return the configured hash algorithm."""
        return self._hash_algorithm

    def compute_initial_hash(self, evidence_path: Path, evidence_id: str) -> str:
        """Compute the initial integrity hash of an evidence file.

        Args:
            evidence_path: Path to the evidence file (read-only).
            evidence_id: Evidence identifier for audit correlation.

        Returns:
            Hexadecimal integrity hash digest.
        """
        digest = compute_file_hash(evidence_path, self._hash_algorithm)
        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="INTEGRITY_HASH_COMPUTED",
            evidence_id=evidence_id,
            hash_before=None,
            hash_after=digest,
            details={
                "path": str(evidence_path),
                "algorithm": self._hash_algorithm.value,
            },
        )
        return digest

    def verify_integrity(
        self,
        evidence_path: Path,
        expected_hash: str,
        evidence_id: str,
    ) -> bool:
        """Recompute and verify the integrity hash of an evidence file.

        Args:
            evidence_path: Path to the evidence file (read-only).
            expected_hash: Previously recorded integrity hash.
            evidence_id: Evidence identifier for audit correlation.

        Returns:
            True when the recomputed hash matches ``expected_hash``.

        Raises:
            IntegrityVerificationError: If the recomputed hash does not match.
        """
        try:
            verify_hash(evidence_path, expected_hash, self._hash_algorithm)
        except IntegrityVerificationError as exc:
            self._audit_logger.log_action(
                stage=PipelineStage.ACQUISITION,
                action="INTEGRITY_VIOLATION",
                evidence_id=evidence_id,
                hash_before=expected_hash,
                hash_after=exc.actual_hash,
                details={
                    "path": str(evidence_path),
                    "algorithm": self._hash_algorithm.value,
                },
            )
            raise

        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="INTEGRITY_VERIFIED",
            evidence_id=evidence_id,
            hash_before=expected_hash,
            hash_after=expected_hash,
            details={
                "path": str(evidence_path),
                "algorithm": self._hash_algorithm.value,
            },
        )
        return True

    def generate_chain_of_custody_record(
        self,
        evidence: EvidenceImage,
    ) -> dict[str, Any]:
        """Generate a structured chain-of-custody verification record.

        Args:
            evidence: Evidence metadata including the original integrity hash.

        Returns:
            Structured custody record dictionary.
        """
        verification_timestamp = datetime.now(UTC)
        try:
            self.verify_integrity(
                evidence.file_path,
                evidence.original_hash,
                evidence.evidence_id,
            )
            verification_result = "VERIFIED"
        except IntegrityVerificationError:
            verification_result = "FAILED"

        return {
            "evidence_id": evidence.evidence_id,
            "file_path": str(evidence.file_path),
            "original_hash": evidence.original_hash,
            "hash_algorithm": evidence.hash_algorithm.value,
            "file_size": evidence.file_size_bytes,
            "verification_timestamp": verification_timestamp.isoformat(),
            "verification_result": verification_result,
            "record_id": str(uuid4()),
        }
