"""Analysis pipeline API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dfat.api.dependencies import get_forensic_orchestrator
from dfat.api.schemas.requests import AnalysisRunRequest
from dfat.api.schemas.responses import AnalysisStatusResponse
from dfat.core.exceptions import EvidenceNotFoundError
from dfat.core.models.pipeline import PipelineState
from dfat.pipeline import PipelineOrchestrator

router = APIRouter(prefix="/analysis", tags=["analysis"])


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


@router.post(
    "",
    response_model=AnalysisStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_analysis(
    body: AnalysisRunRequest,
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> AnalysisStatusResponse:
    """Run the analysis pipeline for registered evidence."""
    state = orchestrator.start_pipeline(
        body.evidence_id,
        mode=body.mode,
        use_fallback=body.use_fallback,
    )
    return _to_status(state)


@router.get("/{pipeline_id}", response_model=AnalysisStatusResponse)
def get_analysis_status(
    pipeline_id: str,
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> AnalysisStatusResponse:
    """Get pipeline status by pipeline ID."""
    state = orchestrator.get_pipeline_state(pipeline_id)
    if state is None:
        raise EvidenceNotFoundError(
            f"Pipeline not found: {pipeline_id}",
            context={"pipeline_id": pipeline_id},
        )
    return _to_status(state)
