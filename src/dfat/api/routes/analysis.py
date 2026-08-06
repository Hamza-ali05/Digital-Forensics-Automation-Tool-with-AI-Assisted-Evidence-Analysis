"""Analysis pipeline API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dfat.api.dependencies import (
    get_analysis_service,
    get_forensic_orchestrator,
    require_permission,
)
from dfat.api.schemas.requests import AnalysisRunRequest
from dfat.api.schemas.responses import AnalysisStatusResponse
from dfat.core.models.pipeline import PipelineState
from dfat.database.models.user import UserORM
from dfat.pipeline import PipelineOrchestrator
from dfat.services.analysis_service import AnalysisService

router = APIRouter(prefix="/analysis", tags=["Analysis"])


def _to_status(state: PipelineState) -> AnalysisStatusResponse:
    """Map pipeline state to API status response."""
    errors: list[str] = []
    stage_summary: dict[str, object] = {}
    for name, result in state.stage_results.items():
        stage_summary[name] = {
            "success": result.success,
            "duration_seconds": result.duration_seconds,
            "output_data": result.output_data,
        }
        errors.extend(result.errors)
    return AnalysisStatusResponse(
        pipeline_id=state.pipeline_id,
        current_stage=state.current_stage.value,
        is_complete=bool(state.is_complete),
        stage_results=stage_summary,
        errors=errors,
    )


def _latest_pipeline_state(
    orchestrator: PipelineOrchestrator,
) -> PipelineState | None:
    """Return the most recently recorded pipeline state, if any."""
    states = list(orchestrator._pipeline_states.values())  # noqa: SLF001
    return states[-1] if states else None


@router.post(
    "",
    response_model=AnalysisStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_analysis(
    body: AnalysisRunRequest,
    current_user: UserORM = Depends(require_permission("analysis", "create")),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> AnalysisStatusResponse:
    """Run the analysis pipeline for registered evidence."""
    if body.mode == "parse-only":
        await analysis_service.run_parse_only(body.evidence_id, current_user.id)
        state = _latest_pipeline_state(orchestrator)
        if state is not None:
            return _to_status(state)
        return AnalysisStatusResponse(
            pipeline_id=body.evidence_id,
            current_stage="parsing",
            is_complete=True,
            stage_results={},
            errors=[],
        )

    if body.mode == "triage-only":
        state = orchestrator.start_pipeline(
            body.evidence_id,
            mode="triage-only",
            use_fallback=body.use_fallback,
        )
        return _to_status(state)

    report = await analysis_service.run_full_analysis(
        body.evidence_id,
        current_user.id,
        use_fallback=body.use_fallback,
    )
    for pipeline_id, report_id in list(orchestrator._pipeline_reports.items()):  # noqa: SLF001
        if report_id == report.report_id:
            state = orchestrator.get_pipeline_state(pipeline_id)
            if state is not None:
                return _to_status(state)
    return AnalysisStatusResponse(
        pipeline_id=report.report_id,
        current_stage="reporting",
        is_complete=True,
        stage_results=dict(report.stage_timings),
        errors=[],
    )


@router.get("/{pipeline_id}", response_model=AnalysisStatusResponse)
async def get_analysis_status(
    pipeline_id: str,
    _: UserORM = Depends(require_permission("analysis", "read")),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisStatusResponse:
    """Get pipeline status by pipeline ID."""
    state = await analysis_service.get_analysis_status(pipeline_id)
    return _to_status(state)
