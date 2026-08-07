"""Pipeline job execution and monitoring API routes."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from dfat.api.dependencies import get_forensic_orchestrator, require_permission
from dfat.api.schemas.requests import PipelineRunRequest
from dfat.api.schemas.responses import ParserInfoResponse, ParserListResponse
from dfat.auth.exceptions import InsufficientPermissionsError
from dfat.auth.rbac import PermissionChecker
from dfat.database.models.user import UserORM
from dfat.pipeline import PipelineOrchestrator
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.models import PipelineJob, PipelineProgress

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


async def _run_job_background(
    orchestrator: PipelineOrchestrator,
    job_id: str,
) -> None:
    """Execute a submitted job; log failures without raising to the client."""
    try:
        await orchestrator.execute_submitted_job(job_id)
    except Exception:  # noqa: BLE001 — background task isolation
        logger.exception("Background pipeline job failed: %s", job_id)


def _assert_can_cancel(job: PipelineJob, user: UserORM) -> None:
    """Require job owner or admin role to cancel."""
    role_obj = getattr(user, "role", None)
    role = str(getattr(role_obj, "name", None) or user.role_id)
    if role.startswith("role-"):
        role = role.removeprefix("role-")
    if job.user_id == user.id or role == "admin":
        return
    if PermissionChecker.has_permission(role, "all", "delete"):
        return
    raise InsufficientPermissionsError(
        required_permission="pipeline.cancel (owner or admin)",
        user_role=role,
    )


@router.post(
    "/run",
    response_model=PipelineJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_pipeline(
    body: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    current_user: UserORM = Depends(require_permission("analysis", "create")),
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> PipelineJob:
    """Submit a pipeline job for asynchronous execution."""
    job = await orchestrator.submit_pipeline(
        evidence_id=body.evidence_id,
        case_id=body.case_id,
        user_id=current_user.id,
        mode=body.mode,
        use_fallback=body.use_fallback,
    )
    background_tasks.add_task(_run_job_background, orchestrator, job.job_id)
    return job


@router.get("/jobs", response_model=list[PipelineJob])
async def list_pipeline_jobs(
    status_filter: Optional[JobStatus] = Query(default=None, alias="status"),
    case_id: Optional[str] = Query(default=None),
    _: UserORM = Depends(require_permission("analysis", "read")),
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> list[PipelineJob]:
    """List pipeline jobs with optional status and case filters."""
    return await orchestrator.list_pipeline_jobs(
        status=status_filter,
        case_id=case_id,
    )


@router.get("/parsers", response_model=ParserListResponse)
async def list_parsers(
    _: UserORM = Depends(require_permission("analysis", "read")),
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> ParserListResponse:
    """List registered artefact parsers and availability status."""
    parsers = [
        ParserInfoResponse(
            parser_name=item["parser_name"],
            available=bool(item["available"]),
            supported_evidence_types=list(item.get("supported_evidence_types") or []),
        )
        for item in orchestrator.list_parsers()
    ]
    return ParserListResponse(parsers=parsers, total=len(parsers))


@router.get("/{job_id}", response_model=PipelineJob)
async def get_pipeline_job(
    job_id: str,
    _: UserORM = Depends(require_permission("analysis", "read")),
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> PipelineJob:
    """Get a pipeline job including stage execution details."""
    return await orchestrator.get_job(job_id)


@router.get("/{job_id}/progress", response_model=PipelineProgress)
async def get_pipeline_progress(
    job_id: str,
    _: UserORM = Depends(require_permission("analysis", "read")),
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> PipelineProgress:
    """Get real-time progress for a pipeline job."""
    return await orchestrator.get_pipeline_status(job_id)


@router.post("/{job_id}/cancel", response_model=PipelineJob)
async def cancel_pipeline_job(
    job_id: str,
    current_user: UserORM = Depends(require_permission("analysis", "create")),
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> PipelineJob:
    """Cancel a queued or running pipeline job (owner or admin)."""
    job = await orchestrator.get_job(job_id)
    _assert_can_cancel(job, current_user)
    return await orchestrator.cancel_pipeline(job_id, current_user.id)
