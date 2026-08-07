"""Case lifecycle management API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from dfat.api.dependencies import get_case_service, require_permission
from dfat.case_management.enums import CaseStatus
from dfat.case_management.schemas import (
    AddEvidenceToCaseRequest,
    AssignInvestigatorRequest,
    CaseListResponse,
    CaseResponse,
    CaseSummaryResponse,
    CaseTransitionRequest,
    CreateCaseRequest,
    InvestigatorResponse,
)
from dfat.core.models.case import Case
from dfat.database.models.user import UserORM
from dfat.services.case_service import CaseService

router = APIRouter(prefix="/cases", tags=["Cases"])


def _to_case_response(case: Case) -> CaseResponse:
    """Map a domain ``Case`` to ``CaseResponse``."""
    return CaseResponse(
        case_id=case.case_id,
        case_name=case.case_name,
        description=case.metadata.description,
        status=case.status,
        lead_investigator_id=case.lead_investigator_id,
        investigators=[
            InvestigatorResponse(
                user_id=inv.user_id,
                username=inv.username,
                full_name=inv.full_name,
                role=inv.role,
                assigned_at=inv.assigned_at,
            )
            for inv in case.investigators
        ],
        evidence_ids=list(case.evidence_ids),
        evidence_count=case.evidence_count,
        investigator_count=case.investigator_count,
        opened_at=case.opened_at,
        closed_at=case.closed_at,
        archived_at=case.archived_at,
        closure_reason=case.closure_reason,
        notes=list(case.notes),
        tags=list(case.tags),
        created_at=case.metadata.created_at,
    )


@router.post(
    "",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_case(
    body: CreateCaseRequest,
    current_user: UserORM = Depends(require_permission("cases", "create")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Create a new investigation case."""
    case = await case_service.create_case(
        case_name=body.case_name,
        description=body.description,
        created_by=current_user.id,
    )
    return _to_case_response(case)


@router.get("", response_model=CaseListResponse)
async def list_cases(
    status_filter: Optional[CaseStatus] = Query(
        default=None,
        alias="status",
        description="Optional case status filter",
    ),
    _: UserORM = Depends(require_permission("cases", "read")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseListResponse:
    """List cases, optionally filtered by status."""
    cases = await case_service.list_cases(status=status_filter)
    items = [_to_case_response(case) for case in cases]
    return CaseListResponse(cases=items, total=len(items))


@router.get("/mine", response_model=CaseListResponse)
async def get_my_cases(
    current_user: UserORM = Depends(require_permission("cases", "read")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseListResponse:
    """List cases where the current user is an active investigator."""
    cases = await case_service.get_my_cases(current_user.id)
    items = [_to_case_response(case) for case in cases]
    return CaseListResponse(cases=items, total=len(items))


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    _: UserORM = Depends(require_permission("cases", "read")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Get case detail by ID."""
    case = await case_service.get_case(case_id)
    return _to_case_response(case)


@router.get("/{case_id}/summary", response_model=CaseSummaryResponse)
async def get_case_summary(
    case_id: str,
    _: UserORM = Depends(require_permission("cases", "read")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseSummaryResponse:
    """Get a comprehensive case summary."""
    summary = await case_service.get_case_summary(case_id)
    return CaseSummaryResponse(**summary)


@router.post("/{case_id}/open", response_model=CaseResponse)
async def open_case(
    case_id: str,
    current_user: UserORM = Depends(require_permission("cases", "update")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Open a case (CREATED → OPEN). Requires a lead investigator."""
    case = await case_service.open_case(case_id, current_user.id)
    return _to_case_response(case)


@router.post("/{case_id}/activate", response_model=CaseResponse)
async def activate_case(
    case_id: str,
    current_user: UserORM = Depends(require_permission("cases", "update")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Activate a case (OPEN → ACTIVE)."""
    case = await case_service.activate_case(case_id, current_user.id)
    return _to_case_response(case)


@router.post("/{case_id}/submit-review", response_model=CaseResponse)
async def submit_for_review(
    case_id: str,
    current_user: UserORM = Depends(require_permission("cases", "update")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Submit a case for review (ACTIVE → UNDER_REVIEW)."""
    case = await case_service.submit_for_review(case_id, current_user.id)
    return _to_case_response(case)


@router.post("/{case_id}/reopen", response_model=CaseResponse)
async def reopen_case(
    case_id: str,
    body: CaseTransitionRequest,
    current_user: UserORM = Depends(require_permission("cases", "update")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Reopen a case under review (UNDER_REVIEW → ACTIVE)."""
    case = await case_service.reopen_case(case_id, current_user.id, body.reason)
    return _to_case_response(case)


@router.post("/{case_id}/close", response_model=CaseResponse)
async def close_case(
    case_id: str,
    body: CaseTransitionRequest,
    current_user: UserORM = Depends(require_permission("cases", "update")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Close a case and seal linked evidence custody chains."""
    case = await case_service.close_case(case_id, current_user.id, body.reason)
    return _to_case_response(case)


@router.post("/{case_id}/archive", response_model=CaseResponse)
async def archive_case(
    case_id: str,
    current_user: UserORM = Depends(require_permission("cases", "update")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Archive a closed case (CLOSED → ARCHIVED)."""
    case = await case_service.archive_case(case_id, current_user.id)
    return _to_case_response(case)


@router.post("/{case_id}/investigators", response_model=CaseResponse)
async def assign_investigator(
    case_id: str,
    body: AssignInvestigatorRequest,
    current_user: UserORM = Depends(require_permission("cases", "update")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Assign an investigator to a case."""
    case = await case_service.assign_investigator(
        case_id,
        body.user_id,
        body.role,
        current_user.id,
    )
    return _to_case_response(case)


@router.delete("/{case_id}/investigators/{user_id}", response_model=CaseResponse)
async def remove_investigator(
    case_id: str,
    user_id: str,
    current_user: UserORM = Depends(require_permission("cases", "update")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Soft-remove an investigator from a case."""
    case = await case_service.remove_investigator(
        case_id,
        user_id,
        current_user.id,
    )
    return _to_case_response(case)


@router.post("/{case_id}/evidence", response_model=CaseResponse)
async def add_evidence_to_case(
    case_id: str,
    body: AddEvidenceToCaseRequest,
    current_user: UserORM = Depends(require_permission("cases", "update")),
    case_service: CaseService = Depends(get_case_service),
) -> CaseResponse:
    """Associate existing evidence with a case."""
    case = await case_service.add_evidence_to_case(
        case_id,
        body.evidence_id,
        current_user.id,
    )
    return _to_case_response(case)
