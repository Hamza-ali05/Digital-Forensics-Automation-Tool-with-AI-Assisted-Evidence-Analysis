"""Enhanced evidence management API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, status

from dfat.api.dependencies import (
    get_custody_service,
    get_evidence_management_service,
    require_permission,
)
from dfat.database.models.user import UserORM
from dfat.evidence_management.custody_service import ChainOfCustodyService
from dfat.evidence_management.schemas import (
    CustodyChainEntryResponse,
    CustodyChainResponse,
    EvidenceDetailResponse,
    EvidenceInventoryItemResponse,
    EvidenceInventoryResponse,
    EvidenceStatisticsResponse,
    EvidenceStatusHistoryEntry,
    EvidenceStatusResponse,
    EvidenceValidationResponse,
    IntegrityVerificationResponse,
    QuarantineEvidenceRequest,
    RegisterEvidenceRequest,
)
from dfat.services.evidence_management_service import EvidenceManagementService

router = APIRouter(prefix="/evidence", tags=["Evidence Management"])


def _model_dump(value: Any) -> Optional[dict[str, Any]]:
    """Serialize a Pydantic model or return None."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)


@router.post(
    "/register",
    response_model=EvidenceValidationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_and_validate_evidence(
    body: RegisterEvidenceRequest,
    current_user: UserORM = Depends(require_permission("evidence", "create")),
    evidence_mgmt: EvidenceManagementService = Depends(
        get_evidence_management_service
    ),
) -> EvidenceValidationResponse:
    """Register evidence, acquire custody, validate, and link to a case."""
    result = await evidence_mgmt.register_and_validate(
        file_path=Path(body.file_path),
        case_id=body.case_id,
        evidence_type=body.evidence_type,
        description=body.description,
        user_id=current_user.id,
        user_name=current_user.full_name,
    )
    evidence = result["evidence"]
    return EvidenceValidationResponse(
        evidence_id=evidence.evidence_id,
        validation_passed=bool(result["validation_passed"]),
        metadata=_model_dump(result.get("metadata")),
        custody_record=_model_dump(result.get("custody_record")),
        validation_failures=list(result.get("validation_failures") or []),
        case_id=result.get("case_id"),
    )


@router.get("/inventory", response_model=EvidenceInventoryResponse)
async def get_evidence_inventory(
    case_id: Optional[str] = Query(default=None),
    _: UserORM = Depends(require_permission("evidence", "read")),
    evidence_mgmt: EvidenceManagementService = Depends(
        get_evidence_management_service
    ),
) -> EvidenceInventoryResponse:
    """List evidence inventory, optionally filtered by case."""
    items = await evidence_mgmt.get_evidence_inventory(case_id=case_id)
    rows = [
        EvidenceInventoryItemResponse(
            evidence_id=item.evidence_id,
            case_id=item.case_id,
            case_name=item.case_name,
            file_name=item.file_name,
            evidence_type=item.evidence_type,
            status=item.status,
            hash_set=_model_dump(item.hash_set),
            mime_type=item.mime_type,
            file_size_bytes=item.file_size_bytes,
            registered_at=item.registered_at,
            last_verified_at=item.last_verified_at,
            custody_actions_count=item.custody_actions_count,
        )
        for item in items
    ]
    return EvidenceInventoryResponse(items=rows, total=len(rows))


@router.get("/statistics", response_model=EvidenceStatisticsResponse)
async def get_evidence_statistics(
    case_id: Optional[str] = Query(default=None),
    _: UserORM = Depends(require_permission("evidence", "read")),
    evidence_mgmt: EvidenceManagementService = Depends(
        get_evidence_management_service
    ),
) -> EvidenceStatisticsResponse:
    """Return aggregated evidence statistics."""
    stats = await evidence_mgmt.get_evidence_statistics(case_id=case_id)
    return EvidenceStatisticsResponse(**stats)


@router.get("/{evidence_id}/detail", response_model=EvidenceDetailResponse)
async def get_evidence_detail(
    evidence_id: str,
    _: UserORM = Depends(require_permission("evidence", "read")),
    evidence_mgmt: EvidenceManagementService = Depends(
        get_evidence_management_service
    ),
) -> EvidenceDetailResponse:
    """Get comprehensive evidence detail."""
    detail = await evidence_mgmt.get_evidence_detail(evidence_id)
    return EvidenceDetailResponse(**detail)


@router.post("/{evidence_id}/validate", response_model=EvidenceValidationResponse)
async def validate_evidence(
    evidence_id: str,
    current_user: UserORM = Depends(require_permission("evidence", "update")),
    evidence_mgmt: EvidenceManagementService = Depends(
        get_evidence_management_service
    ),
) -> EvidenceValidationResponse:
    """Re-validate registered evidence."""
    result = await evidence_mgmt.validate_evidence(evidence_id, current_user.id)
    return EvidenceValidationResponse(
        evidence_id=result.get("evidence_id"),
        validation_passed=bool(result["validation_passed"]),
        metadata=_model_dump(result.get("metadata")),
        validation_failures=list(result.get("validation_failures") or []),
    )


@router.post(
    "/{evidence_id}/verify-integrity",
    response_model=IntegrityVerificationResponse,
)
async def verify_evidence_integrity(
    evidence_id: str,
    current_user: UserORM = Depends(require_permission("evidence", "read")),
    evidence_mgmt: EvidenceManagementService = Depends(
        get_evidence_management_service
    ),
) -> IntegrityVerificationResponse:
    """Verify multi-hash integrity and record an ACCESS custody action."""
    result = await evidence_mgmt.verify_evidence(
        evidence_id,
        current_user.id,
        current_user.full_name,
    )
    return IntegrityVerificationResponse(
        evidence_id=result["evidence_id"],
        integrity_verified=bool(result["integrity_verified"]),
        hash_set=dict(result.get("hash_set") or {}),
        timestamp=str(result["timestamp"]),
        discrepancies=dict(result.get("discrepancies") or {}),
        custody_record=_model_dump(result.get("custody_record")),
    )


@router.get("/{evidence_id}/custody", response_model=CustodyChainResponse)
async def get_custody_chain(
    evidence_id: str,
    _: UserORM = Depends(require_permission("evidence", "read")),
    custody_service: ChainOfCustodyService = Depends(get_custody_service),
) -> CustodyChainResponse:
    """Return the ordered chain-of-custody for an evidence item."""
    chain = await custody_service.get_custody_chain(evidence_id)
    entries = [
        CustodyChainEntryResponse(
            entry_number=record.entry_number,
            record_id=record.record_id,
            action=record.action.value,
            performed_by_user_id=record.performed_by_user_id,
            performed_by_name=record.performed_by_name,
            timestamp=record.timestamp,
            reason=record.reason,
            hash_at_action=record.hash_at_action,
            location=record.location,
            notes=record.notes,
        )
        for record in chain
    ]
    return CustodyChainResponse(
        evidence_id=evidence_id,
        entries=entries,
        total_entries=len(entries),
    )


@router.get("/{evidence_id}/status", response_model=EvidenceStatusResponse)
async def get_evidence_status(
    evidence_id: str,
    _: UserORM = Depends(require_permission("evidence", "read")),
    evidence_mgmt: EvidenceManagementService = Depends(
        get_evidence_management_service
    ),
) -> EvidenceStatusResponse:
    """Return current evidence status and history."""
    history = await evidence_mgmt.get_status_history(evidence_id)
    detail = await evidence_mgmt.get_evidence_detail(evidence_id)
    return EvidenceStatusResponse(
        evidence_id=evidence_id,
        current_status=detail.get("status"),
        history=[
            EvidenceStatusHistoryEntry(
                previous_status=(
                    change.previous_status.value if change.previous_status else None
                ),
                new_status=change.new_status.value,
                changed_by_user_id=change.changed_by_user_id,
                changed_at=change.changed_at,
                reason=change.reason,
            )
            for change in history
        ],
    )


@router.post("/{evidence_id}/quarantine", response_model=EvidenceStatusResponse)
async def quarantine_evidence(
    evidence_id: str,
    body: QuarantineEvidenceRequest,
    current_user: UserORM = Depends(require_permission("evidence", "update")),
    evidence_mgmt: EvidenceManagementService = Depends(
        get_evidence_management_service
    ),
) -> EvidenceStatusResponse:
    """Quarantine evidence for operational safety."""
    await evidence_mgmt.quarantine_evidence(
        evidence_id,
        current_user.id,
        body.reason,
    )
    history = await evidence_mgmt.get_status_history(evidence_id)
    detail = await evidence_mgmt.get_evidence_detail(evidence_id)
    return EvidenceStatusResponse(
        evidence_id=evidence_id,
        current_status=detail.get("status"),
        history=[
            EvidenceStatusHistoryEntry(
                previous_status=(
                    change.previous_status.value if change.previous_status else None
                ),
                new_status=change.new_status.value,
                changed_by_user_id=change.changed_by_user_id,
                changed_at=change.changed_at,
                reason=change.reason,
            )
            for change in history
        ],
    )
