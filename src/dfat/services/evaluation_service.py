"""Benchmark and usability evaluation services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from dfat.core.exceptions import EvidenceNotFoundError, GroundTruthNotFoundError
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.evaluation_repo import (
    SQLAlchemyBenchmarkRepository,
    SQLAlchemyUsabilityRepository,
)
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.performance import PerformanceAnalyzer, PerformanceReport
from dfat.evaluation.usability.questionnaire import QuestionnaireInstrument
from dfat.evaluation.usability.response_analyzer import ResponseAnalyzer
from dfat.evaluation.usability.response_collector import ResponseCollector


class EvaluationService:
    """Business logic for benchmark comparison and usability analysis."""

    def __init__(
        self,
        benchmark_repo: SQLAlchemyBenchmarkRepository,
        usability_repo: SQLAlchemyUsabilityRepository,
        benchmark_comparator: BenchmarkComparator,
        ground_truth_loader: GroundTruthLoader,
        audit_repo: SQLAlchemyAuditRepository,
        artefact_repo: SQLAlchemyArtefactRepository,
        response_collector: ResponseCollector,
        performance_analyzer: PerformanceAnalyzer,
        questionnaire: Optional[QuestionnaireInstrument] = None,
    ) -> None:
        """Initialise the evaluation service."""
        self._benchmark_repo = benchmark_repo
        self._usability_repo = usability_repo
        self._comparator = benchmark_comparator
        self._ground_truth_loader = ground_truth_loader
        self._audit_repo = audit_repo
        self._artefact_repo = artefact_repo
        self._response_collector = response_collector
        self._performance_analyzer = performance_analyzer
        self._questionnaire = questionnaire or QuestionnaireInstrument()

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
        name = dataset_name or ground_truth.dataset_name or dataset_name
        ground_truth.dataset_name = name
        return await self._comparator.compare(
            recovered=artefact_set,
            ground_truth=ground_truth,
            pipeline_start=pipeline_start,
            pipeline_end=pipeline_end,
            dataset_name=name,
            user_id=user_id,
        )

    async def run_benchmark_for_dataset(
        self,
        evidence_id: str,
        ground_truth_dataset: str,
        dataset_source: str,
        user_id: str,
        *,
        ground_truth_path: Optional[str] = None,
        dataset_name: Optional[str] = None,
    ) -> BenchmarkResult:
        """Run benchmark using a named local dataset (or explicit path)."""
        artefact_set = await self._artefact_repo.get(evidence_id)
        if artefact_set is None:
            raise EvidenceNotFoundError(
                f"No artefacts found for evidence: {evidence_id}",
                context={"evidence_id": evidence_id},
            )

        source = (dataset_source or "dfrws").strip().lower()
        if ground_truth_path:
            ground_truth = self._ground_truth_loader.load(Path(ground_truth_path))
        elif source == "cfreds":
            ground_truth = self._ground_truth_loader.load_cfreds(ground_truth_dataset)
        elif source == "dfrws":
            ground_truth = self._ground_truth_loader.load_dfrws(ground_truth_dataset)
        else:
            raise GroundTruthNotFoundError(
                f"Unknown dataset source: {dataset_source}",
                context={"dataset_source": dataset_source},
            )

        name = (
            dataset_name
            or ground_truth_dataset
            or ground_truth.dataset_name
            or "unknown"
        )
        ground_truth.dataset_name = name
        end = datetime.now(UTC)
        start = end - timedelta(seconds=1)
        return await self._comparator.compare(
            recovered=artefact_set,
            ground_truth=ground_truth,
            pipeline_start=start,
            pipeline_end=end,
            dataset_name=name,
            user_id=user_id,
        )

    async def submit_usability_response(self, response: UsabilityResponse) -> str:
        """Persist an anonymised usability questionnaire response."""
        return await self._usability_repo.save(response)

    async def collect_usability_response(
        self,
        ratings: dict[str, int],
        free_text: Optional[str] = None,
    ) -> str:
        """Collect an anonymised questionnaire response via ``ResponseCollector``."""
        return await self._response_collector.collect_response(
            ratings=ratings,
            free_text=free_text,
        )

    async def get_benchmark_results(self) -> list[BenchmarkResult]:
        """List all stored benchmark results."""
        return await self._benchmark_repo.list_all()

    async def get_benchmark_result(self, benchmark_id: str) -> BenchmarkResult:
        """Load a single benchmark result by ID."""
        result = await self._benchmark_repo.get(benchmark_id)
        if result is None:
            raise EvidenceNotFoundError(
                f"Benchmark result not found: {benchmark_id}",
                context={"benchmark_id": benchmark_id},
            )
        return result

    async def get_performance_report(
        self,
        dataset_name: str,
        baseline_ttt: Optional[float] = None,
    ) -> PerformanceReport:
        """Build a performance analytics report for a dataset."""
        results = await self._performance_analyzer.get_historical_results(dataset_name)
        return self._performance_analyzer.generate_performance_report(
            results,
            baseline_ttt=baseline_ttt,
        )

    def list_datasets(self) -> dict[str, list[str]]:
        """List available local DFRWS/CFReDS datasets."""
        return self._ground_truth_loader.list_all_datasets()

    def get_questionnaire_instrument(self) -> dict[str, Any]:
        """Return the ethics-locked questionnaire instrument definition."""
        return {
            "instrument_version": self._questionnaire.INSTRUMENT_VERSION,
            "questions": list(self._questionnaire.QUESTIONS),
        }

    async def get_usability_analysis(self) -> dict[str, Any]:
        """Compute descriptive usability statistics via ``ResponseAnalyzer``."""
        responses = await self._usability_repo.get_all_responses()
        analyzer = ResponseAnalyzer(responses)
        report = analyzer.generate_evaluation_report()
        return report.model_dump(mode="json")

    async def export_usability_responses(self, format: str = "json") -> str:
        """Export anonymised usability responses."""
        return await self._response_collector.export_responses_anonymised(format)

    async def delete_usability_responses(self) -> int:
        """Destroy all usability responses (ethics data destruction)."""
        return await self._response_collector.delete_all_responses()
