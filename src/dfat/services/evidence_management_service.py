"""Enhanced evidence management composing Prompt 2 ``EvidenceService``."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from dfat.case_management.enums import (
    EVIDENCE_STATUS_TRANSITIONS,
    CaseStatus,
    CustodyAction,
    EvidenceStatus,
)
from dfat.case_management.exceptions import CaseNotFoundError
from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.exceptions import EvidenceNotFoundError, IntegrityVerificationError
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.evidence_status_repo import (
    EvidenceMetadataRepository,
    EvidenceStatusRepository,
)
from dfat.evidence_management.custody_service import ChainOfCustodyService
from dfat.evidence_management.exceptions import (
    EvidenceManagementError,
    EvidenceValidationError,
    InvalidEvidenceTransitionError,
)
from dfat.evidence_management.hash_service import MultiHashService
from dfat.evidence_management.models import (
    EvidenceInventoryItem,
    EvidenceMetadataRecord,
    EvidenceStatusChange,
    HashSet,
)
from dfat.evidence_management.validation_service import EvidenceValidationService
from dfat.services.audit_service import AuditService
from dfat.services.evidence_service import EvidenceService


class EvidenceManagementService:
    """Compose registration, validation, custody, metadata, and status tracking.

    Wraps :class:`~dfat.services.evidence_service.EvidenceService` via composition
    without modifying it.
    """

    _ELIGIBLE_CASE_STATUSES = frozenset({CaseStatus.OPEN, CaseStatus.ACTIVE})

    def __init__(
        self,
        evidence_service: EvidenceService,
        validation_service: EvidenceValidationService,
        hash_service: MultiHashService,
        custody_service: ChainOfCustodyService,
        metadata_repo: EvidenceMetadataRepository,
        status_repo: EvidenceStatusRepository,
        evidence_repo: SQLAlchemyEvidenceRepository,
        case_repo: SQLAlchemyCaseRepository,
        audit_service: AuditService,
    ) -> None:
        """Initialise the enhanced evidence management service.

        Args:
            evidence_service: Prompt 2 evidence registration service.
            validation_service: Format/MIME/hash validation service.
            hash_service: Multi-algorithm hash service.
            custody_service: Chain-of-custody service.
            metadata_repo: Evidence metadata repository.
            status_repo: Evidence status history repository.
            evidence_repo: Evidence metadata repository.
            case_repo: Case lifecycle repository.
            audit_service: Dual-write audit trail service.
        """
        self._evidence_service = evidence_service
        self._validation = validation_service
        self._hash_service = hash_service
        self._custody = custody_service
        self._metadata_repo = metadata_repo
        self._status_repo = status_repo
        self._evidence_repo = evidence_repo
        self._case_repo = case_repo
        self._audit_service = audit_service

    async def register_and_validate(
        self,
        file_path: Path | str,
        case_id: str,
        evidence_type: EvidenceType,
        description: Optional[str],
        user_id: str,
        user_name: str,
    ) -> dict[str, Any]:
        """Run the full register → acquire → validate → metadata → case workflow.

        Args:
            file_path: Path to the evidence file (read-only).
            case_id: Target investigation case (must be OPEN or ACTIVE).
            evidence_type: Disk image or memory dump.
            description: Optional evidence/case description.
            user_id: Acting user identifier.
            user_name: Acting user display name.

        Returns:
            Dict with ``evidence``, ``metadata``, ``custody_record``,
            ``validation_passed``, and related fields.
        """
        case = await self._case_repo.get(case_id)
        if case is None:
            raise CaseNotFoundError(f"Case not found: {case_id}", case_id=case_id)
        if case.status not in self._ELIGIBLE_CASE_STATUSES:
            raise EvidenceManagementError(
                "Evidence can only be registered into OPEN or ACTIVE cases",
                context={
                    "case_id": case_id,
                    "case_status": case.status.value,
                },
            )

        path = Path(file_path)
        evidence = await self._evidence_service.register_evidence(
            file_path=path,
            case_name=case.case_name,
            investigator=user_name,
            evidence_type=evidence_type,
            description=description,
            user_id=user_id,
        )

        await self._status_repo.add_status_change(
            EvidenceStatusChange(
                evidence_id=evidence.evidence_id,
                previous_status=None,
                new_status=EvidenceStatus.REGISTERED,
                changed_by_user_id=user_id,
                reason="Evidence registered",
            )
        )

        custody_record = await self._custody.record_acquisition(
            evidence.evidence_id,
            evidence.file_path,
            user_id,
            user_name,
            reason=f"Acquired into case {case_id}",
        )

        validation_passed = False
        metadata: Optional[EvidenceMetadataRecord] = None
        validation_failures: list[str] = []
        try:
            metadata = await self._validation.validate_evidence(
                evidence.evidence_id,
                evidence.file_path,
                evidence_type,
                user_id,
            )
            await self._metadata_repo.save_metadata(metadata)
            validation_passed = True
        except EvidenceValidationError as exc:
            validation_failures = list(exc.validation_failures)
            metadata = await self._metadata_repo.get_metadata(evidence.evidence_id)

        await self._case_repo.add_evidence_id(case_id, evidence.evidence_id)

        await self._audit_service.log_action(
            stage=PipelineStage.ACQUISITION,
            action="evidence_register_and_validate",
            evidence_id=evidence.evidence_id,
            user_id=user_id,
            details={
                "case_id": case_id,
                "validation_passed": validation_passed,
                "validation_failures": validation_failures,
                "custody_record_id": custody_record.record_id,
            },
        )

        return {
            "evidence": evidence,
            "metadata": metadata,
            "custody_record": custody_record,
            "validation_passed": validation_passed,
            "validation_failures": validation_failures,
            "case_id": case_id,
        }

    async def get_registered_evidence(self, evidence_id: str):
        """Return the domain evidence object used by the forensic pipeline."""
        return await self._evidence_service.get_evidence(evidence_id)

    async def get_evidence_detail(self, evidence_id: str) -> dict[str, Any]:
        """Return a comprehensive evidence view (metadata, status, custody)."""
        evidence, metadata, status, history, chain, stored = await asyncio.gather(
            self._evidence_service.get_evidence(evidence_id),
            self._metadata_repo.get_metadata(evidence_id),
            self._status_repo.get_current_status(evidence_id),
            self._status_repo.get_history(evidence_id),
            self._custody.get_custody_chain(evidence_id),
            self._evidence_repo.get(evidence_id),
        )

        case_id = evidence.case.case_id
        if stored is not None:
            case_id = stored.case.case_id
        case = await self._case_repo.get(case_id)

        return {
            "evidence_id": evidence.evidence_id,
            "file_path": str(evidence.file_path),
            "evidence_type": evidence.evidence_type.value,
            "original_hash": evidence.original_hash,
            "hash_algorithm": evidence.hash_algorithm.value,
            "file_size_bytes": evidence.file_size_bytes,
            "acquired_at": (
                evidence.acquired_at.isoformat() if evidence.acquired_at else None
            ),
            "case_id": case_id,
            "case_name": evidence.case.case_name,
            "case_status": case.status.value if case is not None else None,
            "status": status.value if status is not None else None,
            "metadata": metadata.model_dump(mode="json") if metadata else None,
            "status_history": [
                {
                    "previous_status": (
                        h.previous_status.value if h.previous_status else None
                    ),
                    "new_status": h.new_status.value,
                    "changed_by_user_id": h.changed_by_user_id,
                    "changed_at": h.changed_at.isoformat(),
                    "reason": h.reason,
                }
                for h in history
            ],
            "custody_chain": [
                {
                    "entry_number": r.entry_number,
                    "action": r.action.value,
                    "performed_by_user_id": r.performed_by_user_id,
                    "performed_by_name": r.performed_by_name,
                    "timestamp": r.timestamp.isoformat(),
                    "reason": r.reason,
                    "hash_at_action": r.hash_at_action,
                }
                for r in chain
            ],
            "custody_actions_count": len(chain),
        }

    async def get_evidence_inventory(
        self,
        case_id: Optional[str] = None,
    ) -> list[EvidenceInventoryItem]:
        """Return inventory rows for a case or all evidence."""
        if case_id is not None:
            case = await self._case_repo.get(case_id)
            if case is None:
                raise CaseNotFoundError(f"Case not found: {case_id}", case_id=case_id)
            evidence_list = await self._evidence_repo.get_by_case(case_id)
        else:
            evidence_list = await self._evidence_repo.list_all()

        evidence_ids = [evidence.evidence_id for evidence in evidence_list]
        status_map = await self._status_repo.get_current_statuses(evidence_ids)
        metadata_map = await self._metadata_repo.get_by_evidence_ids(evidence_ids)
        chains_map = await self._custody.get_custody_chains(evidence_ids)

        inventory: list[EvidenceInventoryItem] = []
        for evidence in evidence_list:
            chain = chains_map.get(evidence.evidence_id, [])
            metadata = metadata_map.get(evidence.evidence_id)
            last_verified = None
            for record in reversed(chain):
                if record.action is CustodyAction.ACCESSED:
                    last_verified = record.timestamp
                    break
            inventory.append(
                EvidenceInventoryItem(
                    evidence_id=evidence.evidence_id,
                    case_id=evidence.case.case_id,
                    case_name=evidence.case.case_name,
                    file_name=Path(evidence.file_path).name,
                    evidence_type=evidence.evidence_type,
                    status=status_map.get(evidence.evidence_id)
                    or EvidenceStatus.REGISTERED,
                    hash_set=metadata.hash_set if metadata else None,
                    mime_type=metadata.mime_type if metadata else None,
                    file_size_bytes=evidence.file_size_bytes,
                    registered_at=evidence.case.created_at,
                    last_verified_at=last_verified,
                    custody_actions_count=len(chain),
                )
            )
        return inventory

    async def verify_evidence(
        self,
        evidence_id: str,
        user_id: str,
        user_name: str,
    ) -> dict[str, Any]:
        """Verify multi-hash integrity and record an ACCESS custody action.

        Args:
            evidence_id: Evidence identifier.
            user_id: Acting user identifier.
            user_name: Acting user display name.

        Returns:
            Dict with ``integrity_verified``, ``hash_set``, ``timestamp``,
            and ``discrepancies``.
        """
        evidence = await self._evidence_service.get_evidence(evidence_id)
        stored = await self._metadata_repo.get_hash_set(evidence_id)
        actual = self._hash_service.compute_hash_set(
            evidence.file_path,
            evidence_id,
        )
        timestamp = datetime.now(UTC)
        discrepancies: dict[str, Any] = {}
        integrity_verified = False

        if stored is None:
            # Fall back to single SHA-256 from registration.
            if actual.sha256.lower() != evidence.original_hash.lower():
                discrepancies["sha256"] = {
                    "expected": evidence.original_hash.lower(),
                    "actual": actual.sha256.lower(),
                }
            else:
                integrity_verified = True
                stored = HashSet(
                    md5=actual.md5,
                    sha1=actual.sha1,
                    sha256=actual.sha256,
                    file_size_bytes=actual.file_size_bytes,
                )
        else:
            try:
                self._hash_service.verify_hash_set(
                    evidence.file_path,
                    stored,
                    evidence_id,
                )
                integrity_verified = True
                actual = stored
            except IntegrityVerificationError as exc:
                discrepancies = dict(exc.context.get("mismatches") or {})
                if not discrepancies:
                    discrepancies["sha256"] = {
                        "expected": exc.expected_hash,
                        "actual": exc.actual_hash,
                    }

        custody_record = None
        if integrity_verified:
            custody_record = await self._custody.record_access(
                evidence_id,
                evidence.file_path,
                user_id,
                user_name,
                reason="Integrity verification access",
            )
        else:
            await self._audit_service.log_action(
                stage=PipelineStage.ACQUISITION,
                action="evidence_integrity_failed",
                evidence_id=evidence_id,
                user_id=user_id,
                details={"discrepancies": discrepancies},
            )

        return {
            "evidence_id": evidence_id,
            "integrity_verified": integrity_verified,
            "hash_set": actual.model_dump(mode="json"),
            "timestamp": timestamp.isoformat(),
            "discrepancies": discrepancies,
            "custody_record": custody_record,
        }

    async def transition_evidence_status(
        self,
        evidence_id: str,
        new_status: EvidenceStatus,
        user_id: str,
        reason: str,
    ) -> EvidenceStatusChange:
        """Transition evidence status if permitted by ``EVIDENCE_STATUS_TRANSITIONS``."""
        evidence = await self._evidence_repo.get(evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(
                f"Evidence not found: {evidence_id}",
                context={"evidence_id": evidence_id},
            )
        current = await self._status_repo.get_current_status(evidence_id)
        if current is None:
            current = EvidenceStatus.REGISTERED

        allowed = EVIDENCE_STATUS_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            raise InvalidEvidenceTransitionError(
                f"Invalid evidence status transition: "
                f"{current.value} → {new_status.value}",
                current_status=current.value,
                attempted_status=new_status.value,
                context={"evidence_id": evidence_id},
            )

        change = EvidenceStatusChange(
            evidence_id=evidence_id,
            previous_status=current,
            new_status=new_status,
            changed_by_user_id=user_id,
            reason=reason,
        )
        await self._status_repo.add_status_change(change)
        await self._audit_service.log_action(
            stage=PipelineStage.ACQUISITION,
            action="evidence_status_transition",
            evidence_id=evidence_id,
            user_id=user_id,
            details={
                "from_status": current.value,
                "to_status": new_status.value,
                "reason": reason,
            },
        )
        return change

    async def quarantine_evidence(
        self,
        evidence_id: str,
        user_id: str,
        reason: str,
    ) -> EvidenceStatusChange:
        """Force evidence into ``QUARANTINED`` status (operational safety)."""
        evidence = await self._evidence_repo.get(evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(
                f"Evidence not found: {evidence_id}",
                context={"evidence_id": evidence_id},
            )
        current = await self._status_repo.get_current_status(evidence_id)
        if current is EvidenceStatus.QUARANTINED:
            return EvidenceStatusChange(
                evidence_id=evidence_id,
                previous_status=EvidenceStatus.QUARANTINED,
                new_status=EvidenceStatus.QUARANTINED,
                changed_by_user_id=user_id,
                reason=reason,
            )

        change = EvidenceStatusChange(
            evidence_id=evidence_id,
            previous_status=current,
            new_status=EvidenceStatus.QUARANTINED,
            changed_by_user_id=user_id,
            reason=reason,
        )
        await self._status_repo.add_status_change(change)
        await self._audit_service.log_action(
            stage=PipelineStage.ACQUISITION,
            action="evidence_quarantined",
            evidence_id=evidence_id,
            user_id=user_id,
            details={"reason": reason, "previous_status": current.value if current else None},
        )
        return change

    async def get_status_history(
        self,
        evidence_id: str,
    ) -> list[EvidenceStatusChange]:
        """Return ordered evidence status history."""
        return await self._status_repo.get_history(evidence_id)

    async def validate_evidence(
        self,
        evidence_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Re-run format/MIME/hash validation for registered evidence.

        Args:
            evidence_id: Evidence identifier.
            user_id: Acting user identifier.

        Returns:
            Dict with ``validation_passed``, ``metadata``, and
            ``validation_failures``.
        """
        evidence = await self._evidence_service.get_evidence(evidence_id)
        try:
            metadata = await self._validation.revalidate_evidence(
                evidence_id,
                evidence.file_path,
                evidence.evidence_type,
                user_id,
            )
            await self._metadata_repo.save_metadata(metadata)
            return {
                "evidence_id": evidence_id,
                "validation_passed": True,
                "metadata": metadata,
                "validation_failures": [],
            }
        except EvidenceValidationError as exc:
            return {
                "evidence_id": evidence_id,
                "validation_passed": False,
                "metadata": await self._metadata_repo.get_metadata(evidence_id),
                "validation_failures": list(exc.validation_failures),
            }

    async def get_evidence_statistics(
        self,
        case_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Aggregate evidence counts, sizes, and custody-chain metrics."""
        inventory = await self.get_evidence_inventory(case_id=case_id)
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        total_size = 0
        chain_lengths: list[int] = []

        for item in inventory:
            by_type[item.evidence_type.value] = (
                by_type.get(item.evidence_type.value, 0) + 1
            )
            by_status[item.status.value] = by_status.get(item.status.value, 0) + 1
            total_size += item.file_size_bytes
            chain_lengths.append(item.custody_actions_count)

        avg_chain = (
            sum(chain_lengths) / len(chain_lengths) if chain_lengths else 0.0
        )
        return {
            "total": len(inventory),
            "by_type": by_type,
            "by_status": by_status,
            "total_size": total_size,
            "avg_custody_chain_length": avg_chain,
            "case_id": case_id,
        }
