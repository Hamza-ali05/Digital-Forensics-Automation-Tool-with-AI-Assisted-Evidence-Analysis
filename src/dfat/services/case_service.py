"""Investigation case lifecycle management service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from dfat.case_management.enums import CASE_STATUS_TRANSITIONS, CaseStatus, CustodyAction
from dfat.case_management.exceptions import (
    CaseAlreadyClosedError,
    CaseError,
    CaseNotFoundError,
    InvalidCaseTransitionError,
    NoLeadInvestigatorError,
)
from dfat.core.enums import PipelineStage
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evidence import CaseMetadata
from dfat.database.models.user import UserORM
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.user_repo import SQLAlchemyUserRepository
from dfat.evidence_management.custody_service import ChainOfCustodyService
from dfat.services.audit_service import AuditService


class CaseService:
    """Business logic for case lifecycle, investigators, and evidence linkage."""

    def __init__(
        self,
        case_repo: SQLAlchemyCaseRepository,
        evidence_repo: SQLAlchemyEvidenceRepository,
        user_repo: SQLAlchemyUserRepository,
        audit_service: AuditService,
        custody_service: ChainOfCustodyService,
    ) -> None:
        """Initialise the case management service.

        Args:
            case_repo: Case lifecycle repository.
            evidence_repo: Evidence metadata repository.
            user_repo: User account repository.
            audit_service: Dual-write audit trail service.
            custody_service: Chain-of-custody service.
        """
        self._case_repo = case_repo
        self._evidence_repo = evidence_repo
        self._user_repo = user_repo
        self._audit_service = audit_service
        self._custody_service = custody_service

    async def create_case(
        self,
        case_name: str,
        description: Optional[str],
        created_by: str,
    ) -> Case:
        """Create a new case in ``CREATED`` status.

        Args:
            case_name: Human-readable case name.
            description: Optional case description.
            created_by: Creating user identifier.

        Returns:
            Persisted case domain model.
        """
        creator = await self._require_user(created_by)
        metadata = CaseMetadata(
            case_name=case_name,
            investigator=creator.full_name,
            description=description,
        )
        case = Case(metadata=metadata, status=CaseStatus.CREATED)
        await self._case_repo.save(case, created_by_user_id=created_by)
        created = await self._require_case(case.case_id)
        await self._audit(
            action="case_created",
            case_id=created.case_id,
            user_id=created_by,
            details={
                "case_name": case_name,
                "status": created.status.value,
            },
        )
        return created

    async def open_case(self, case_id: str, user_id: str) -> Case:
        """Transition ``CREATED`` → ``OPEN``. Requires a lead investigator."""
        case = await self._require_case(case_id)
        self._validate_transition(case.status, CaseStatus.OPEN)
        if not self._has_lead(case):
            raise NoLeadInvestigatorError(
                "Cannot open case without a lead investigator",
                context={"case_id": case_id},
            )
        updated = await self._transition(case_id, CaseStatus.OPEN, user_id)
        return updated

    async def activate_case(self, case_id: str, user_id: str) -> Case:
        """Transition ``OPEN`` → ``ACTIVE``."""
        case = await self._require_case(case_id)
        self._validate_transition(case.status, CaseStatus.ACTIVE)
        return await self._transition(case_id, CaseStatus.ACTIVE, user_id)

    async def submit_for_review(self, case_id: str, user_id: str) -> Case:
        """Transition ``ACTIVE`` → ``UNDER_REVIEW``."""
        case = await self._require_case(case_id)
        self._validate_transition(case.status, CaseStatus.UNDER_REVIEW)
        return await self._transition(case_id, CaseStatus.UNDER_REVIEW, user_id)

    async def reopen_case(self, case_id: str, user_id: str, reason: str) -> Case:
        """Transition ``UNDER_REVIEW`` → ``ACTIVE`` with a reopen reason."""
        case = await self._require_case(case_id)
        self._validate_transition(case.status, CaseStatus.ACTIVE)
        case.notes = list(case.notes) + [f"Reopened: {reason}"]
        await self._case_repo.save(
            case,
            created_by_user_id=case.lead_investigator_id or user_id,
        )
        return await self._transition(
            case_id,
            CaseStatus.ACTIVE,
            user_id,
            extra_details={"reason": reason},
        )

    async def close_case(self, case_id: str, user_id: str, reason: str) -> Case:
        """Close a case and seal custody chains for all linked evidence."""
        case = await self._require_case(case_id)
        from_status = case.status
        self._validate_transition(from_status, CaseStatus.CLOSED)
        sealed_ids = await self._seal_all_evidence(
            case,
            user_id=user_id,
            reason=reason,
        )

        case.closure_reason = reason
        case.status = CaseStatus.CLOSED
        case.closed_at = datetime.now(UTC)
        await self._case_repo.save(
            case,
            created_by_user_id=case.lead_investigator_id or user_id,
        )
        # Ensure closed_at is set even if a prior save path omitted it.
        closed = await self._case_repo.update_status(case_id, CaseStatus.CLOSED)
        if closed.closure_reason != reason:
            closed.closure_reason = reason
            await self._case_repo.save(
                closed,
                created_by_user_id=closed.lead_investigator_id or user_id,
            )
            closed = await self._require_case(case_id)

        await self._audit(
            action="case_closed",
            case_id=case_id,
            user_id=user_id,
            details={
                "from_status": from_status.value,
                "to_status": CaseStatus.CLOSED.value,
                "reason": reason,
                "evidence_sealed": sealed_ids,
            },
        )
        return await self._require_case(case_id)

    async def archive_case(self, case_id: str, user_id: str) -> Case:
        """Transition ``CLOSED`` → ``ARCHIVED`` and mark linked evidence archived."""
        case = await self._require_case(case_id)
        self._validate_transition(case.status, CaseStatus.ARCHIVED)
        archived_evidence = await self._archive_all_evidence(case, user_id=user_id)
        updated = await self._transition(
            case_id,
            CaseStatus.ARCHIVED,
            user_id,
            extra_details={"archived_evidence_ids": archived_evidence},
        )
        return updated

    async def get_case(self, case_id: str) -> Case:
        """Return a case by identifier."""
        return await self._require_case(case_id)

    async def list_cases(
        self,
        status: Optional[CaseStatus] = None,
    ) -> list[Case]:
        """List all cases, optionally filtered by status."""
        if status is not None:
            return await self._case_repo.get_by_status(status)
        return await self._case_repo.list_all()

    async def get_my_cases(self, user_id: str) -> list[Case]:
        """List cases where the user is an active investigator."""
        return await self._case_repo.get_by_investigator(user_id)

    async def assign_investigator(
        self,
        case_id: str,
        user_id: str,
        role: str,
        assigned_by: str,
    ) -> Case:
        """Assign an investigator to a case.

        Args:
            case_id: Case identifier.
            user_id: User to assign.
            role: ``lead`` or ``member``.
            assigned_by: Acting user identifier.

        Returns:
            Updated case with the new investigator assignment.
        """
        if role not in ("lead", "member"):
            raise CaseError(
                "Investigator role must be 'lead' or 'member'",
                context={"role": role, "case_id": case_id},
            )
        case = await self._require_case(case_id)
        if case.status in (CaseStatus.CLOSED, CaseStatus.ARCHIVED):
            raise CaseAlreadyClosedError(
                "Cannot assign investigators to a closed or archived case",
                context={"case_id": case_id, "status": case.status.value},
            )
        user = await self._require_user(user_id)
        investigator = CaseInvestigator(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=role,  # type: ignore[arg-type]
        )
        await self._case_repo.add_investigator(case_id, investigator)
        if role == "lead":
            # Ensure lead_investigator_id is persisted (repo also sets this).
            refreshed = await self._require_case(case_id)
            if refreshed.lead_investigator_id != user_id:
                refreshed.lead_investigator_id = user_id
                await self._case_repo.save(
                    refreshed,
                    created_by_user_id=assigned_by,
                )
        await self._audit(
            action="case_investigator_assigned",
            case_id=case_id,
            user_id=assigned_by,
            details={"assigned_user_id": user_id, "role": role},
        )
        return await self._require_case(case_id)

    async def remove_investigator(
        self,
        case_id: str,
        user_id: str,
        removed_by: str,
    ) -> Case:
        """Soft-remove an investigator from a case."""
        await self._require_case(case_id)
        removed = await self._case_repo.remove_investigator(case_id, user_id)
        await self._audit(
            action="case_investigator_removed",
            case_id=case_id,
            user_id=removed_by,
            details={"removed_user_id": user_id, "was_active": removed},
        )
        return await self._require_case(case_id)

    async def add_evidence_to_case(
        self,
        case_id: str,
        evidence_id: str,
        user_id: str,
    ) -> Case:
        """Associate evidence with a case and ensure an ACQUIRED custody entry."""
        case = await self._require_case(case_id)
        if case.status in (CaseStatus.CLOSED, CaseStatus.ARCHIVED):
            raise CaseAlreadyClosedError(
                "Cannot add evidence to a closed or archived case",
                context={"case_id": case_id, "status": case.status.value},
            )
        evidence = await self._evidence_repo.get(evidence_id)
        if evidence is None:
            raise CaseError(
                f"Evidence not found: {evidence_id}",
                context={"evidence_id": evidence_id, "case_id": case_id},
            )
        await self._case_repo.add_evidence_id(case_id, evidence_id)

        chain = await self._custody_service.get_custody_chain(evidence_id)
        if not chain:
            actor = await self._require_user(user_id)
            await self._custody_service.record_acquisition(
                evidence_id,
                evidence.file_path,
                user_id,
                actor.full_name,
                reason=f"Acquired into case {case_id}",
            )

        await self._audit(
            action="case_evidence_added",
            case_id=case_id,
            user_id=user_id,
            details={"evidence_id": evidence_id},
        )
        return await self._require_case(case_id)

    async def get_case_summary(self, case_id: str) -> dict[str, Any]:
        """Return a comprehensive case summary dictionary."""
        case = await self._require_case(case_id)
        evidence_summaries: list[dict[str, Any]] = []
        for evidence_id in case.evidence_ids:
            evidence = await self._evidence_repo.get(evidence_id)
            if evidence is None:
                evidence_summaries.append(
                    {"evidence_id": evidence_id, "missing": True}
                )
                continue
            chain = await self._custody_service.get_custody_chain(evidence_id)
            evidence_summaries.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "file_path": str(evidence.file_path),
                    "evidence_type": evidence.evidence_type.value,
                    "original_hash": evidence.original_hash,
                    "file_size_bytes": evidence.file_size_bytes,
                    "custody_entries": len(chain),
                    "latest_custody_action": (
                        chain[-1].action.value if chain else None
                    ),
                }
            )
        return {
            "case_id": case.case_id,
            "case_name": case.case_name,
            "description": case.metadata.description,
            "status": case.status.value,
            "lead_investigator_id": case.lead_investigator_id,
            "investigators": [
                {
                    "user_id": inv.user_id,
                    "username": inv.username,
                    "full_name": inv.full_name,
                    "role": inv.role,
                    "assigned_at": inv.assigned_at.isoformat(),
                }
                for inv in case.investigators
            ],
            "investigator_count": case.investigator_count,
            "evidence_ids": list(case.evidence_ids),
            "evidence_count": case.evidence_count,
            "evidence_summaries": evidence_summaries,
            "opened_at": case.opened_at.isoformat() if case.opened_at else None,
            "closed_at": case.closed_at.isoformat() if case.closed_at else None,
            "archived_at": (
                case.archived_at.isoformat() if case.archived_at else None
            ),
            "closure_reason": case.closure_reason,
            "notes": list(case.notes),
            "tags": list(case.tags),
            "created_at": case.metadata.created_at.isoformat(),
        }

    def _validate_transition(
        self,
        current: CaseStatus,
        target: CaseStatus,
    ) -> None:
        """Raise if ``current`` → ``target`` is not in ``CASE_STATUS_TRANSITIONS``."""
        allowed = CASE_STATUS_TRANSITIONS.get(current, [])
        if target not in allowed:
            raise InvalidCaseTransitionError(
                f"Invalid case status transition: {current.value} → {target.value}",
                current_status=current.value,
                attempted_status=target.value,
            )

    async def _transition(
        self,
        case_id: str,
        target: CaseStatus,
        user_id: str,
        *,
        extra_details: Optional[dict[str, Any]] = None,
    ) -> Case:
        """Apply a validated status transition and audit it."""
        case = await self._require_case(case_id)
        from_status = case.status
        updated = await self._case_repo.update_status(case_id, target)
        details: dict[str, Any] = {
            "from_status": from_status.value,
            "to_status": target.value,
        }
        if extra_details:
            details.update(extra_details)
        await self._audit(
            action=f"case_{target.value}",
            case_id=case_id,
            user_id=user_id,
            details=details,
        )
        return updated

    async def _seal_all_evidence(
        self,
        case: Case,
        *,
        user_id: str,
        reason: str,
    ) -> list[str]:
        """Seal custody chains for all evidence linked to the case."""
        actor = await self._require_user(user_id)
        sealed: list[str] = []
        for evidence_id in case.evidence_ids:
            evidence = await self._evidence_repo.get(evidence_id)
            if evidence is None:
                continue
            chain = await self._custody_service.get_custody_chain(evidence_id)
            if chain and chain[-1].action == CustodyAction.SEALED:
                sealed.append(evidence_id)
                continue
            if not chain:
                await self._custody_service.record_acquisition(
                    evidence_id,
                    evidence.file_path,
                    user_id,
                    actor.full_name,
                    reason=f"Acquisition before seal on case close ({case.case_id})",
                )
            await self._custody_service.record_seal(
                evidence_id,
                evidence.file_path,
                user_id,
                actor.full_name,
                reason=reason,
            )
            sealed.append(evidence_id)
        return sealed

    async def _archive_all_evidence(
        self,
        case: Case,
        *,
        user_id: str,
    ) -> list[str]:
        """Mark linked evidence as archived with the case (audit + metadata note).

        Evidence domain models do not carry Prompt 3 status; archival is recorded
        via audit and by ensuring custody is sealed. Status-column updates are
        deferred to the evidence-management service layer.
        """
        archived: list[str] = []
        for evidence_id in case.evidence_ids:
            evidence = await self._evidence_repo.get(evidence_id)
            if evidence is None:
                continue
            chain = await self._custody_service.get_custody_chain(evidence_id)
            if not chain or chain[-1].action != CustodyAction.SEALED:
                # Defensive: close_case should have sealed; seal if still open.
                actor = await self._require_user(user_id)
                if not chain:
                    await self._custody_service.record_acquisition(
                        evidence_id,
                        evidence.file_path,
                        user_id,
                        actor.full_name,
                        reason=f"Acquisition before archive ({case.case_id})",
                    )
                await self._custody_service.record_seal(
                    evidence_id,
                    evidence.file_path,
                    user_id,
                    actor.full_name,
                    reason=f"Sealed on case archive ({case.case_id})",
                )
            await self._audit(
                action="evidence_archived_with_case",
                case_id=case.case_id,
                user_id=user_id,
                details={"evidence_id": evidence_id},
            )
            archived.append(evidence_id)
        return archived

    @staticmethod
    def _has_lead(case: Case) -> bool:
        """Return True when a lead investigator is assigned."""
        if case.lead_investigator_id:
            return True
        return any(inv.role == "lead" for inv in case.investigators)

    async def _require_case(self, case_id: str) -> Case:
        """Load a case or raise ``CaseNotFoundError``."""
        case = await self._case_repo.get(case_id)
        if case is None:
            raise CaseNotFoundError(f"Case not found: {case_id}", case_id=case_id)
        return case

    async def _require_user(self, user_id: str) -> UserORM:
        """Load a user or raise ``CaseError``."""
        user = await self._user_repo.get(user_id)
        if user is None:
            raise CaseError(
                f"User not found: {user_id}",
                context={"user_id": user_id},
            )
        return user

    async def _audit(
        self,
        *,
        action: str,
        case_id: str,
        user_id: str,
        details: dict[str, Any],
    ) -> None:
        """Write a case-management audit entry."""
        await self._audit_service.log_action(
            stage=PipelineStage.ACQUISITION,
            action=action,
            evidence_id=f"case:{case_id}",
            user_id=user_id,
            details={"case_id": case_id, **details},
        )
