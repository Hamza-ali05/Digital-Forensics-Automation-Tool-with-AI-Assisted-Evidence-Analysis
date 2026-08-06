"""Evidence registration and metadata API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, status

from dfat.api.dependencies import (
    get_disk_image_handler,
    get_evidence_repository,
    get_memory_dump_handler,
)
from dfat.api.schemas.requests import EvidenceUploadRequest
from dfat.api.schemas.responses import EvidenceResponse
from dfat.core.enums import EvidenceType
from dfat.core.exceptions import EvidenceNotFoundError
from dfat.core.models.evidence import CaseMetadata
from dfat.forensic_engine.acquisition.image_handler import DiskImageHandler
from dfat.forensic_engine.acquisition.memory_handler import MemoryDumpHandler
from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _to_response(evidence) -> EvidenceResponse:  # type: ignore[no-untyped-def]
    """Map an EvidenceImage/MemoryDump to an EvidenceResponse."""
    return EvidenceResponse(
        evidence_id=evidence.evidence_id,
        file_path=str(evidence.file_path),
        evidence_type=evidence.evidence_type,
        original_hash=evidence.original_hash,
        case=evidence.case.model_dump(mode="json"),
    )


@router.post(
    "",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_evidence(
    body: EvidenceUploadRequest,
    evidence_repo: FileSystemEvidenceRepository = Depends(get_evidence_repository),
    disk_handler: DiskImageHandler = Depends(get_disk_image_handler),
    memory_handler: MemoryDumpHandler = Depends(get_memory_dump_handler),
) -> EvidenceResponse:
    """Register evidence for analysis."""
    case = CaseMetadata(
        case_name=body.case_name,
        investigator=body.investigator,
        description=body.description,
    )
    path = Path(body.file_path)
    if body.evidence_type == EvidenceType.MEMORY_DUMP:
        evidence = memory_handler.load_dump(path, case)
    else:
        evidence = disk_handler.load_image(path, case)
    evidence_repo.save(evidence)
    return _to_response(evidence)


@router.get("/{evidence_id}", response_model=EvidenceResponse)
def get_evidence(
    evidence_id: str,
    evidence_repo: FileSystemEvidenceRepository = Depends(get_evidence_repository),
) -> EvidenceResponse:
    """Get evidence metadata by ID."""
    evidence = evidence_repo.get(evidence_id)
    if evidence is None:
        raise EvidenceNotFoundError(
            f"Evidence not found: {evidence_id}",
            context={"evidence_id": evidence_id},
        )
    return _to_response(evidence)


@router.get("", response_model=list[EvidenceResponse])
def list_evidence(
    evidence_repo: FileSystemEvidenceRepository = Depends(get_evidence_repository),
) -> list[EvidenceResponse]:
    """List all registered evidence."""
    return [_to_response(item) for item in evidence_repo.list_all()]
