"""Benchmark evaluation API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, status

from dfat.api.dependencies import get_forensic_orchestrator, require_permission
from dfat.api.schemas.requests import BenchmarkRunRequest
from dfat.api.schemas.responses import BenchmarkResponse
from dfat.core.models.evaluation import BenchmarkResult
from dfat.database.models.user import UserORM
from dfat.pipeline import PipelineOrchestrator

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


def _to_benchmark(result: BenchmarkResult) -> BenchmarkResponse:
    """Map BenchmarkResult to API response."""
    return BenchmarkResponse(
        benchmark_id=result.benchmark_id,
        precision=result.precision,
        recall=result.recall,
        f1_score=result.f1_score,
        time_to_triage_seconds=result.time_to_triage_seconds,
        artefacts_expected=result.artefacts_expected,
        artefacts_recovered=result.artefacts_recovered,
    )


@router.post(
    "/benchmark",
    response_model=BenchmarkResponse,
    status_code=status.HTTP_200_OK,
)
async def run_benchmark(
    body: BenchmarkRunRequest,
    _: UserORM = Depends(require_permission("evaluation", "create")),
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> BenchmarkResponse:
    """Run benchmark comparison against ground truth."""
    result = orchestrator.run_benchmark(
        body.evidence_id,
        Path(body.ground_truth_path),
        body.dataset_name,
    )
    return _to_benchmark(result)


@router.get("/results", response_model=list[BenchmarkResponse])
async def list_benchmark_results(
    _: UserORM = Depends(require_permission("evaluation", "read")),
    orchestrator: PipelineOrchestrator = Depends(get_forensic_orchestrator),
) -> list[BenchmarkResponse]:
    """List all stored benchmark results."""
    return [_to_benchmark(item) for item in orchestrator.list_benchmark_results()]
