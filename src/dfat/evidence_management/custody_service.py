"""Formal chain-of-custody recording and verification (ACPO-aligned)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from dfat.case_management.enums import CustodyAction
from dfat.core.enums import PipelineStage
from dfat.core.exceptions import IntegrityVerificationError
from dfat.core.interfaces.repository import IEvidenceRepository
from dfat.database.repositories.custody_repo import CustodyRepository
from dfat.evidence_management.exceptions import (
    CustodyChainError,
    CustodyRecordNotFoundError,
)
from dfat.evidence_management.hash_service import MultiHashService
from dfat.evidence_management.models import ChainOfCustodyRecord
from dfat.services.audit_service import AuditService


class ChainOfCustodyService:
    """Append-only chain-of-custody service with integrity checks at access/seal.

    Custody records are INSERT-ONLY. This service never updates or deletes
    existing custody rows.
    """

    def __init__(
        self,
        custody_repo: CustodyRepository,
        hash_service: MultiHashService,
        audit_service: AuditService,
        evidence_repo: IEvidenceRepository,
    ) -> None:
        """Initialise the chain-of-custody service.

        Args:
            custody_repo: Insert-only custody repository.
            hash_service: Multi-algorithm hash service for integrity checks.
            audit_service: Dual-write audit trail service.
            evidence_repo: Evidence metadata repository.
        """
        self._custody_repo = custody_repo
        self._hash_service = hash_service
        self._audit_service = audit_service
        self._evidence_repo = evidence_repo

    async def record_acquisition(
        self,
        evidence_id: str,
        file_path: Path | str,
        user_id: str,
        user_name: str,
        reason: str,
    ) -> ChainOfCustodyRecord:
        """Record the first custody entry (ACQUIRED, entry_number=1).

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file (read-only).
            user_id: Acquiring user ID.
            user_name: Acquiring user display name.
            reason: Acquisition reason.

        Returns:
            Persisted custody record with ``entry_number=1``.

        Raises:
            CustodyChainError: If a custody chain already exists for the evidence.
        """
        existing = await self._custody_repo.count_by_evidence(evidence_id)
        if existing > 0:
            raise CustodyChainError(
                "Custody chain already exists; acquisition must be the first entry",
                context={"evidence_id": evidence_id, "existing_entries": existing},
            )

        digest = self._current_sha256(file_path, evidence_id)
        record = ChainOfCustodyRecord(
            evidence_id=evidence_id,
            action=CustodyAction.ACQUIRED,
            performed_by_user_id=user_id,
            performed_by_name=user_name,
            reason=reason,
            hash_at_action=digest,
        )
        return await self._persist_and_audit(record, PipelineStage.ACQUISITION)

    async def record_access(
        self,
        evidence_id: str,
        file_path: Path | str,
        user_id: str,
        user_name: str,
        reason: str,
    ) -> ChainOfCustodyRecord:
        """Verify integrity, then record an ACCESS custody action.

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file (read-only).
            user_id: Accessing user ID.
            user_name: Accessing user display name.
            reason: Access reason.

        Returns:
            Persisted ACCESS custody record.

        Raises:
            IntegrityVerificationError: If the file hash does not match baseline.
            CustodyRecordNotFoundError: If no acquisition baseline exists.
        """
        await self._verify_integrity_or_raise(evidence_id, file_path)
        digest = self._current_sha256(file_path, evidence_id)
        record = ChainOfCustodyRecord(
            evidence_id=evidence_id,
            action=CustodyAction.ACCESSED,
            performed_by_user_id=user_id,
            performed_by_name=user_name,
            reason=reason,
            hash_at_action=digest,
        )
        return await self._persist_and_audit(record, PipelineStage.ACQUISITION)

    async def record_transfer(
        self,
        evidence_id: str,
        file_path: Path | str,
        from_user: Mapping[str, str],
        to_user: Mapping[str, str],
        reason: str,
    ) -> ChainOfCustodyRecord:
        """Record a TRANSFERRED custody action.

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file (read-only).
            from_user: Mapping with ``user_id`` and ``user_name`` of the giver.
            to_user: Mapping with ``user_id`` and ``user_name`` of the receiver.
            reason: Transfer reason.

        Returns:
            Persisted TRANSFERRED custody record.
        """
        digest = self._current_sha256(file_path, evidence_id)
        to_id = to_user["user_id"]
        to_name = to_user["user_name"]
        record = ChainOfCustodyRecord(
            evidence_id=evidence_id,
            action=CustodyAction.TRANSFERRED,
            performed_by_user_id=from_user["user_id"],
            performed_by_name=from_user["user_name"],
            reason=reason,
            hash_at_action=digest,
            notes=f"Transferred to {to_name} ({to_id})",
        )
        return await self._persist_and_audit(record, PipelineStage.ACQUISITION)

    async def record_analysis(
        self,
        evidence_id: str,
        file_path: Path | str,
        user_id: str,
        user_name: str,
        pipeline_id: str,
    ) -> ChainOfCustodyRecord:
        """Record an ANALYSED custody action for a pipeline run.

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file (read-only).
            user_id: Analyst user ID.
            user_name: Analyst display name.
            pipeline_id: Pipeline run identifier.

        Returns:
            Persisted ANALYSED custody record.
        """
        digest = self._current_sha256(file_path, evidence_id)
        record = ChainOfCustodyRecord(
            evidence_id=evidence_id,
            action=CustodyAction.ANALYSED,
            performed_by_user_id=user_id,
            performed_by_name=user_name,
            reason=f"Analysis via pipeline {pipeline_id}",
            hash_at_action=digest,
            notes=f"pipeline_id={pipeline_id}",
        )
        return await self._persist_and_audit(record, PipelineStage.PARSING)

    async def record_release(
        self,
        evidence_id: str,
        file_path: Path | str,
        user_id: str,
        user_name: str,
        reason: str,
    ) -> ChainOfCustodyRecord:
        """Record a RELEASED custody action.

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file (read-only).
            user_id: Releasing user ID.
            user_name: Releasing user display name.
            reason: Release reason.

        Returns:
            Persisted RELEASED custody record.
        """
        digest = self._current_sha256(file_path, evidence_id)
        record = ChainOfCustodyRecord(
            evidence_id=evidence_id,
            action=CustodyAction.RELEASED,
            performed_by_user_id=user_id,
            performed_by_name=user_name,
            reason=reason,
            hash_at_action=digest,
        )
        return await self._persist_and_audit(record, PipelineStage.ACQUISITION)

    async def record_seal(
        self,
        evidence_id: str,
        file_path: Path | str,
        user_id: str,
        user_name: str,
        reason: str,
    ) -> ChainOfCustodyRecord:
        """Perform a final integrity check, then record a SEALED action.

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file (read-only).
            user_id: Sealing user ID.
            user_name: Sealing user display name.
            reason: Seal reason.

        Returns:
            Persisted SEALED custody record.

        Raises:
            IntegrityVerificationError: If the final integrity check fails.
        """
        await self._verify_integrity_or_raise(evidence_id, file_path)
        digest = self._current_sha256(file_path, evidence_id)
        record = ChainOfCustodyRecord(
            evidence_id=evidence_id,
            action=CustodyAction.SEALED,
            performed_by_user_id=user_id,
            performed_by_name=user_name,
            reason=reason,
            hash_at_action=digest,
        )
        return await self._persist_and_audit(record, PipelineStage.ACQUISITION)

    async def get_custody_chain(
        self,
        evidence_id: str,
    ) -> list[ChainOfCustodyRecord]:
        """Return the ordered custody chain for an evidence item."""
        return await self._custody_repo.get_chain(evidence_id)

    async def get_custody_chains(
        self,
        evidence_ids: list[str],
    ) -> dict[str, list[ChainOfCustodyRecord]]:
        """Batch-load ordered custody chains for many evidence items."""
        return await self._custody_repo.get_chains(evidence_ids)

    async def verify_custody_chain(
        self,
        evidence_id: str,
        file_path: Path | str,
    ) -> dict[str, Any]:
        """Verify custody chain structure and current file integrity.

        Detects missing sequential entry numbers, missing/invalid acquisition
        baseline, and hash mismatches against the current file and between
        recorded digests.

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file (read-only).

        Returns:
            Dict with ``is_valid``, ``total_entries``, ``integrity_verified``,
            and ``issues``.
        """
        chain = await self._custody_repo.get_chain(evidence_id)
        issues: list[str] = []
        total = len(chain)

        if total == 0:
            issues.append("No custody records found")
            return {
                "is_valid": False,
                "total_entries": 0,
                "integrity_verified": False,
                "issues": issues,
            }

        if chain[0].action != CustodyAction.ACQUIRED:
            issues.append(
                f"First entry must be ACQUIRED, found {chain[0].action.value}"
            )
        if chain[0].entry_number != 1:
            issues.append(
                f"First entry_number must be 1, found {chain[0].entry_number}"
            )

        expected_numbers = list(range(1, total + 1))
        actual_numbers = [r.entry_number for r in chain]
        for expected in expected_numbers:
            if expected not in actual_numbers:
                issues.append(f"Missing entry_number {expected} (gap in chain)")
        for number in actual_numbers:
            if number is None:
                issues.append("Custody record missing entry_number")
            elif number not in expected_numbers:
                issues.append(f"Unexpected entry_number {number}")

        baseline = chain[0].hash_at_action.lower()
        for record in chain[1:]:
            if record.hash_at_action.lower() != baseline:
                issues.append(
                    f"Hash mismatch at entry {record.entry_number}: "
                    f"recorded digest differs from acquisition baseline"
                )

        current = self._current_sha256(file_path, evidence_id).lower()
        integrity_verified = current == baseline
        if not integrity_verified:
            issues.append(
                "Current file hash does not match acquisition baseline "
                f"(expected={baseline}, actual={current})"
            )

        structural_ok = not any(
            issue.startswith("Missing entry_number")
            or issue.startswith("Unexpected entry_number")
            or issue.startswith("First entry")
            or issue.startswith("Custody record missing")
            or issue.startswith("No custody")
            for issue in issues
        )
        # Hash-at-action drift is also a chain validity failure
        hash_drift = any(issue.startswith("Hash mismatch at entry") for issue in issues)
        is_valid = structural_ok and integrity_verified and not hash_drift

        return {
            "is_valid": is_valid,
            "total_entries": total,
            "integrity_verified": integrity_verified,
            "issues": issues,
        }

    async def generate_custody_report(self, evidence_id: str) -> dict[str, Any]:
        """Generate a formatted custody report for an evidence item.

        Args:
            evidence_id: Evidence identifier.

        Returns:
            Structured custody report dictionary.
        """
        chain = await self._custody_repo.get_chain(evidence_id)
        if not chain:
            raise CustodyRecordNotFoundError(
                "No custody chain found for evidence",
                context={"evidence_id": evidence_id},
            )

        evidence = await self._evidence_repo.get(evidence_id)
        actions_summary: dict[str, int] = {}
        for record in chain:
            key = record.action.value
            actions_summary[key] = actions_summary.get(key, 0) + 1

        latest = chain[-1]
        first = chain[0]
        return {
            "evidence_id": evidence_id,
            "evidence_file_path": str(evidence.file_path) if evidence else None,
            "total_entries": len(chain),
            "entry_numbers": [r.entry_number for r in chain],
            "acquired_at": first.timestamp.isoformat(),
            "acquired_by": {
                "user_id": first.performed_by_user_id,
                "user_name": first.performed_by_name,
            },
            "acquisition_hash": first.hash_at_action,
            "latest_action": latest.action.value,
            "latest_timestamp": latest.timestamp.isoformat(),
            "current_custodian": {
                "user_id": latest.performed_by_user_id,
                "user_name": latest.performed_by_name,
            },
            "actions_summary": actions_summary,
            "chain": [
                {
                    "entry_number": r.entry_number,
                    "record_id": r.record_id,
                    "action": r.action.value,
                    "performed_by_user_id": r.performed_by_user_id,
                    "performed_by_name": r.performed_by_name,
                    "timestamp": r.timestamp.isoformat(),
                    "reason": r.reason,
                    "hash_at_action": r.hash_at_action,
                    "location": r.location,
                    "notes": r.notes,
                }
                for r in chain
            ],
        }

    def _current_sha256(self, file_path: Path | str, evidence_id: str) -> str:
        """Compute the current SHA-256 digest of the evidence file."""
        hash_set = self._hash_service.compute_hash_set(Path(file_path), evidence_id)
        return hash_set.sha256

    async def _baseline_hash(self, evidence_id: str) -> str:
        """Return the acquisition (entry 1) hash baseline for integrity checks."""
        chain = await self._custody_repo.get_chain(evidence_id)
        if not chain:
            evidence = await self._evidence_repo.get(evidence_id)
            if evidence is not None and evidence.original_hash:
                return evidence.original_hash
            raise CustodyRecordNotFoundError(
                "No custody baseline found for integrity verification",
                context={"evidence_id": evidence_id},
            )
        if chain[0].action != CustodyAction.ACQUIRED:
            raise CustodyChainError(
                "Custody baseline is not an ACQUIRED entry",
                context={
                    "evidence_id": evidence_id,
                    "first_action": chain[0].action.value,
                },
            )
        return chain[0].hash_at_action

    async def _verify_integrity_or_raise(
        self,
        evidence_id: str,
        file_path: Path | str,
    ) -> None:
        """Raise ``IntegrityVerificationError`` when the file hash drifts."""
        expected = (await self._baseline_hash(evidence_id)).lower()
        actual = self._current_sha256(file_path, evidence_id).lower()
        if actual != expected:
            raise IntegrityVerificationError(
                "Evidence integrity check failed before custody recording",
                expected_hash=expected,
                actual_hash=actual,
                context={"evidence_id": evidence_id, "file_path": str(file_path)},
            )

    async def _persist_and_audit(
        self,
        record: ChainOfCustodyRecord,
        stage: PipelineStage,
    ) -> ChainOfCustodyRecord:
        """Insert the custody record (append-only) and write an audit entry."""
        await self._custody_repo.add_record(record)
        await self._audit_service.log_action(
            stage=stage,
            action=f"custody_{record.action.value}",
            evidence_id=record.evidence_id,
            user_id=record.performed_by_user_id,
            details={
                "record_id": record.record_id,
                "reason": record.reason,
                "hash_at_action": record.hash_at_action,
                "notes": record.notes,
            },
        )
        latest = await self._custody_repo.get_latest(record.evidence_id)
        if latest is None:
            raise CustodyChainError(
                "Custody record was not found after insert",
                context={"evidence_id": record.evidence_id},
            )
        return latest
