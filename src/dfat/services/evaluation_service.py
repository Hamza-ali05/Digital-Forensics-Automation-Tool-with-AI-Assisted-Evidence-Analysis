"""Benchmark and usability evaluation services."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dfat.core.enums import PipelineStage
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.core.models.pipeline import AuditEntry
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.evaluation_repo import (
    SQLAlchemyBenchmarkRepository,
    SQLAlchemyUsabilityRepository,
)
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.usability.response_analyzer import ResponseAnalyzer


class EvaluationService:
    """Business logic for benchmark comparison and usability analysis."""

    def __init__(
        self,
        benchmark_repo: SQLAlchemyBenchmarkRepository,
        usability_repo: SQLAlchemyUsabilityRepository,
        benchmark_comparator: BenchmarkComparator,
        ground_truth_loader: GroundTruthLoader,
        audit_repo: SQLAlchemyAuditRepository,
    ) -> None:
        """Initialise the evaluation service.

        Args:
            benchmark_repo: Benchmark persistence repository.
            usability_repo: Usability response repository.
            benchmark_comparator: Metrics comparator.
            ground_truth_loader: Ground-truth dataset loader.
            audit_repo: Database audit repository.
        """
        self._benchmark_repo = benchmark_repo
        self._usability_repo = usability_repo
        self._comparator = benchmark_comparator
        self._ground_truth_loader = ground_truth_loader
        self._audit_repo = audit_repo

    async def run_benchmark(
        self,
        evidence_id: str,
        ground_truth_path: str,
        dataset_name: str,
        artefact_set: ArtefactSet,
        pipeline_start: datetime,
        pipeline_end: datetime,
        user_id: str,
    ) -> BenchmarkResult:
        """Compare recovered artefacts against ground truth and persist results."""
        ground_truth = self._ground_truth_loader.load(Path(ground_truth_path))
        ground_truth["dataset_name"] = dataset_name or ground_truth.get(
            "dataset_name",
            dataset_name,
        )
        result = self._comparator.compare(
            artefact_set,
            ground_truth,
            pipeline_start,
            pipeline_end,
        )
        await self._benchmark_repo.save(result)
        entry_number = await self._audit_repo.get_latest_entry_number() + 1
        await self._audit_repo.log_entry(
            AuditEntry(
                entry_number=entry_number,
                stage=PipelineStage.EVALUATION,
                action="BENCHMARK_COMPLETED",
                evidence_id=evidence_id,
                details={
                    "dataset_name": dataset_name,
                    "precision": result.precision,
                    "recall": result.recall,
                    "f1_score": result.f1_score,
                },
            ),
            user_id=user_id,
        )
        return result

    async def submit_usability_response(self, response: UsabilityResponse) -> str:
        """Persist an anonymised usability questionnaire response."""
        return await self._usability_repo.save(response)

    async def get_benchmark_results(self) -> list[BenchmarkResult]:
        """List all stored benchmark results."""
        return await self._benchmark_repo.list_all()

    async def get_usability_analysis(self) -> dict[str, Any]:
        """Compute descriptive usability statistics via ``ResponseAnalyzer``."""
        responses = await self._usability_repo.get_all_responses()
        analyzer = ResponseAnalyzer(responses)
        return {
            "mean_ratings": analyzer.compute_mean_ratings(),
            "usefulness_percentage": analyzer.compute_usefulness_percentage(),
            "descriptive_statistics": analyzer.compute_descriptive_statistics(),
            "response_count": len(responses),
        }
