"""Benchmark evaluation and usability questionnaire API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse

from dfat.api.dependencies import get_evaluation_service, require_permission, require_role
from dfat.api.schemas.requests import BenchmarkRunRequest, UsabilityRespondRequest
from dfat.api.schemas.responses import (
    BenchmarkResponse,
    DatasetListResponse,
    UsabilityDeleteResponse,
    UsabilitySubmitResponse,
)
from dfat.core.models.evaluation import BenchmarkResult
from dfat.database.models.user import UserORM
from dfat.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


def _to_benchmark(result: BenchmarkResult) -> BenchmarkResponse:
    """Map BenchmarkResult to API response."""
    return BenchmarkResponse(
        benchmark_id=result.benchmark_id,
        dataset_name=result.dataset_name,
        precision=result.precision,
        recall=result.recall,
        f1_score=result.f1_score,
        time_to_triage_seconds=result.time_to_triage_seconds,
        artefacts_expected=result.artefacts_expected,
        artefacts_recovered=result.artefacts_recovered,
        false_positives=result.false_positives,
        false_negatives=result.false_negatives,
        evaluated_at=result.evaluated_at,
    )


@router.post(
    "/benchmark",
    response_model=BenchmarkResponse,
    status_code=status.HTTP_200_OK,
)
async def run_benchmark(
    body: BenchmarkRunRequest,
    user: UserORM = Depends(require_permission("evaluation", "create")),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> BenchmarkResponse:
    """Run benchmark comparison against a local ground-truth dataset."""
    dataset = body.ground_truth_dataset or body.dataset_name or ""
    result = await evaluation_service.run_benchmark_for_dataset(
        evidence_id=body.evidence_id,
        ground_truth_dataset=dataset,
        dataset_source=body.dataset_source,
        user_id=str(user.id),
        ground_truth_path=body.ground_truth_path,
        dataset_name=body.dataset_name or dataset,
    )
    return _to_benchmark(result)


@router.get("/benchmark/results", response_model=list[BenchmarkResponse])
async def list_benchmark_results(
    _: UserORM = Depends(require_permission("evaluation", "read")),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> list[BenchmarkResponse]:
    """List all stored benchmark results."""
    results = await evaluation_service.get_benchmark_results()
    return [_to_benchmark(item) for item in results]


@router.get("/benchmark/results/{benchmark_id}", response_model=BenchmarkResponse)
async def get_benchmark_result(
    benchmark_id: str,
    _: UserORM = Depends(require_permission("evaluation", "read")),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> BenchmarkResponse:
    """Get a specific benchmark result by ID."""
    result = await evaluation_service.get_benchmark_result(benchmark_id)
    return _to_benchmark(result)


@router.get("/benchmark/performance")
async def get_benchmark_performance(
    dataset_name: str = Query(..., min_length=1),
    baseline_ttt: Optional[float] = Query(None, gt=0),
    _: UserORM = Depends(require_permission("evaluation", "read")),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> dict:
    """Return performance analytics for a dataset's historical runs."""
    report = await evaluation_service.get_performance_report(
        dataset_name=dataset_name,
        baseline_ttt=baseline_ttt,
    )
    return report.model_dump(mode="json")


@router.get("/benchmark/datasets", response_model=DatasetListResponse)
async def list_benchmark_datasets(
    _: UserORM = Depends(require_permission("evaluation", "read")),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> DatasetListResponse:
    """List available local DFRWS/CFReDS ground-truth datasets."""
    datasets = evaluation_service.list_datasets()
    return DatasetListResponse(
        dfrws=list(datasets.get("dfrws", [])),
        cfreds=list(datasets.get("cfreds", [])),
    )


# Legacy alias retained for older clients.
@router.get("/results", response_model=list[BenchmarkResponse], include_in_schema=False)
async def list_benchmark_results_legacy(
    _: UserORM = Depends(require_permission("evaluation", "read")),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> list[BenchmarkResponse]:
    """Legacy list endpoint — prefer ``/benchmark/results``."""
    results = await evaluation_service.get_benchmark_results()
    return [_to_benchmark(item) for item in results]


@router.post(
    "/usability/respond",
    response_model=UsabilitySubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_usability_response(
    body: UsabilityRespondRequest,
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> UsabilitySubmitResponse:
    """Submit an anonymised usability questionnaire response (no auth)."""
    try:
        participant_id = await evaluation_service.collect_usability_response(
            ratings=body.ratings,
            free_text=body.free_text,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    return UsabilitySubmitResponse(participant_id=participant_id)


@router.get("/usability/questionnaire")
async def get_usability_questionnaire(
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> dict:
    """Return the ethics-locked questionnaire instrument definition."""
    return evaluation_service.get_questionnaire_instrument()


@router.get("/usability/results")
async def get_usability_results(
    _: UserORM = Depends(require_role(["admin", "investigator"])),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> dict:
    """Return usability analysis results (admin/investigator only)."""
    return await evaluation_service.get_usability_analysis()


@router.get("/usability/export", response_class=PlainTextResponse)
async def export_usability_responses(
    _: UserORM = Depends(require_role(["admin"])),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> Response:
    """Export anonymised usability responses (admin only)."""
    payload = await evaluation_service.export_usability_responses("json")
    return Response(content=payload, media_type="application/json")


@router.delete(
    "/usability/responses",
    response_model=UsabilityDeleteResponse,
)
async def delete_usability_responses(
    _: UserORM = Depends(require_role(["admin"])),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> UsabilityDeleteResponse:
    """Delete all usability responses (ethics data destruction; admin only)."""
    deleted = await evaluation_service.delete_usability_responses()
    return UsabilityDeleteResponse(deleted_count=deleted)
