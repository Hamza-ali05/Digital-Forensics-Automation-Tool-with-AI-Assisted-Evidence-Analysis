"""Evidence registration and metadata API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, status

from dfat.api.dependencies import get_evidence_service, require_permission
from dfat.api.schemas.requests import EvidenceUploadRequest
from dfat.api.schemas.responses import EvidenceResponse
from dfat.core.models.evidence import EvidenceImage
from dfat.database.models.user import UserORM
from dfat.services.evidence_service import EvidenceService

router = APIRouter(prefix="/evidence", tags=["Evidence"])


def _to_response(
    evidence: EvidenceImage,
    *,
    registered_by: Optional[str] = None,
) -> EvidenceResponse:
    """Map an EvidenceImage/MemoryDump to an EvidenceResponse."""
    return EvidenceResponse(
        evidence_id=evidence.evidence_id,
        file_path=str(evidence.file_path),
        evidence_type=evidence.evidence_type,
        original_hash=evidence.original_hash,
        case=evidence.case.model_dump(mode="json"),
        registered_by=registered_by,
    )


@router.post(
    "",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_evidence(
    body: EvidenceUploadRequest,
    current_user: UserORM = Depends(require_permission("evidence", "create")),
    evidence_service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceResponse:
    """Register evidence for analysis."""
    evidence = await evidence_service.register_evidence(
        file_path=Path(body.file_path),
        case_name=body.case_name,
        investigator=body.investigator,
        evidence_type=body.evidence_type,
        description=body.description,
        user_id=current_user.id,
    )
    return _to_response(evidence, registered_by=current_user.id)


@router.get("/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(
    evidence_id: str,
    _: UserORM = Depends(require_permission("evidence", "read")),
    evidence_service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceResponse:
    """Get evidence metadata by ID."""
    evidence = await evidence_service.get_evidence(evidence_id)
    return _to_response(evidence)


@router.get("", response_model=list[EvidenceResponse])
async def list_evidence(
    _: UserORM = Depends(require_permission("evidence", "read")),
    evidence_service: EvidenceService = Depends(get_evidence_service),
) -> list[EvidenceResponse]:
    """List all registered evidence."""
    items = await evidence_service.list_evidence()
    return [_to_response(item) for item in items]
