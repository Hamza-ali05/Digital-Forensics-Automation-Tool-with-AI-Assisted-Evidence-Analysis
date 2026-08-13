"""Automated comparison of recovered artefacts against ground truth."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from dfat.core.enums import PipelineStage
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evaluation import BenchmarkResult
from dfat.database.repositories.evaluation_repo import SQLAlchemyBenchmarkRepository
from dfat.evaluation.benchmark.dfrws_handler import GroundTruth, GroundTruthArtefact
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.services.audit_service import AuditService

_DEFAULT_THRESHOLDS: dict[str, float] = {
    "precision_min": 0.0,
    "recall_min": 0.0,
    "f1_min": 0.0,
}


class BenchmarkComparator:
    """Compare recovered artefacts to ground truth and compute metrics."""

    def __init__(
        self,
        metrics: MetricsCalculator,
        ground_truth_loader: GroundTruthLoader,
        audit_service: AuditService,
        benchmark_repo: SQLAlchemyBenchmarkRepository,
        thresholds: Optional[dict[str, float]] = None,
    ) -> None:
        """Initialise the comparator.

        Args:
            metrics: Metrics computation service.
            ground_truth_loader: Loader exposing DFRWS identifier normalisation.
            audit_service: Dual-write forensic audit service.
            benchmark_repo: Persistence repository for benchmark results.
            thresholds: Optional pass/fail metric thresholds.
        """
        self._metrics = metrics
        self._ground_truth_loader = ground_truth_loader
        self._audit_service = audit_service
        self._benchmark_repo = benchmark_repo
        self._thresholds = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._last_false_positives: list[str] = []
        self._last_false_negatives: list[str] = []
        self._last_true_positives: list[str] = []

    async def compare(
        self,
        recovered: ArtefactSet,
        ground_truth: GroundTruth,
        pipeline_start: datetime,
        pipeline_end: datetime,
        dataset_name: str,
        *,
        user_id: Optional[str] = None,
        persist: bool = True,
        audit: bool = True,
        track_identifiers: bool = True,
    ) -> BenchmarkResult:
        """Compare recovered artefacts against ground truth.

        Steps:
            1. Build recovered identifier set via ``_build_identifier_set``.
            2. Build expected identifier set from ``ground_truth.artefacts``.
            3. TP = intersection, FP = recovered − expected, FN = expected − recovered.
            4. Compute metrics via the metrics calculator.
            5. Persist result to ``benchmark_repo`` (when ``persist``).
            6. Log audit entry ``BENCHMARK_EVALUATION_COMPLETED`` (when ``audit``).
            7. Return ``BenchmarkResult``.

        Args:
            recovered: Pipeline-recovered artefact set.
            ground_truth: Loaded ground-truth model.
            pipeline_start: Pipeline start timestamp.
            pipeline_end: Pipeline end timestamp.
            dataset_name: Dataset name recorded on the result.
            user_id: Optional acting user for audit trail.
            persist: Whether to save the result (disable for per-category runs).
            audit: Whether to emit the completion audit entry.
            track_identifiers: Whether to refresh overall FP/FN identifier lists.

        Returns:
            Benchmark result with precision, recall, F1, and TTT.
        """
        recovered_ids = self._build_identifier_set(recovered)
        expected_ids = self._build_ground_truth_set(ground_truth)

        true_positives_set = recovered_ids & expected_ids
        false_positives_set = recovered_ids - expected_ids
        false_negatives_set = expected_ids - recovered_ids

        if track_identifiers:
            self._last_true_positives = sorted(true_positives_set)
            self._last_false_positives = sorted(false_positives_set)
            self._last_false_negatives = sorted(false_negatives_set)

        name = dataset_name.strip() or ground_truth.dataset_name or "unknown"
        result = self._metrics.compute_all(
            tp=len(true_positives_set),
            fp=len(false_positives_set),
            fn=len(false_negatives_set),
            start=pipeline_start,
            end=pipeline_end,
            dataset_name=name,
            artefacts_expected=len(expected_ids),
            artefacts_recovered=len(recovered_ids),
        )

        if persist:
            await self._benchmark_repo.save(result)

        if audit:
            await self._audit_service.log_action(
                stage=PipelineStage.EVALUATION,
                action="BENCHMARK_EVALUATION_COMPLETED",
                evidence_id=recovered.evidence_id,
                user_id=user_id,
                details={
                    "dataset_name": name,
                    "true_positives": len(true_positives_set),
                    "false_positives": len(false_positives_set),
                    "false_negatives": len(false_negatives_set),
                    "precision": result.precision,
                    "recall": result.recall,
                    "f1_score": result.f1_score,
                    "time_to_triage_seconds": result.time_to_triage_seconds,
                },
            )
        return result

    async def compare_per_category(
        self,
        recovered: ArtefactSet,
        ground_truth: GroundTruth,
        start: datetime,
        end: datetime,
    ) -> dict[str, BenchmarkResult]:
        """Run comparison independently for each artefact category.

        Args:
            recovered: Pipeline-recovered artefact set.
            ground_truth: Loaded ground-truth model.
            start: Pipeline start timestamp.
            end: Pipeline end timestamp.

        Returns:
            Mapping of category value → category-scoped ``BenchmarkResult``.
            Does not persist or audit (overall ``compare`` owns that).
        """
        categories = sorted(
            {
                *(artefact.category for artefact in recovered.artefacts),
                *(entry.category for entry in ground_truth.artefacts),
            },
            key=lambda item: item.value,
        )
        results: dict[str, BenchmarkResult] = {}
        base_name = ground_truth.dataset_name or "unknown"
        for category in categories:
            filtered_recovered = ArtefactSet(
                evidence_id=recovered.evidence_id,
                artefacts=[
                    artefact
                    for artefact in recovered.artefacts
                    if artefact.category == category
                ],
                categories_present=[category],
            )
            filtered_gt = GroundTruth(
                dataset_name=base_name,
                source=ground_truth.source,
                artefacts=[
                    entry
                    for entry in ground_truth.artefacts
                    if entry.category == category
                ],
                categories=[category],
                loaded_at=ground_truth.loaded_at,
            )
            results[category.value] = await self.compare(
                recovered=filtered_recovered,
                ground_truth=filtered_gt,
                pipeline_start=start,
                pipeline_end=end,
                dataset_name=f"{base_name}:{category.value}",
                persist=False,
                audit=False,
                track_identifiers=False,
            )
        return results

    def generate_comparison_report(
        self,
        result: BenchmarkResult,
        per_category: Optional[dict[str, BenchmarkResult]] = None,
    ) -> dict[str, Any]:
        """Build a comprehensive comparison report.

        Args:
            result: Overall computed benchmark metrics.
            per_category: Optional per-category benchmark results.

        Returns:
            Report including overall metrics, per-category breakdown,
            FP/FN identifier lists, and pass/fail assessment.
        """
        passed = (
            result.precision >= self._thresholds["precision_min"]
            and result.recall >= self._thresholds["recall_min"]
            and result.f1_score >= self._thresholds["f1_min"]
        )
        category_breakdown: dict[str, dict[str, Any]] = {}
        for category, cat_result in (per_category or {}).items():
            category_breakdown[category] = {
                "precision": cat_result.precision,
                "recall": cat_result.recall,
                "f1_score": cat_result.f1_score,
                "artefacts_expected": cat_result.artefacts_expected,
                "artefacts_recovered": cat_result.artefacts_recovered,
                "false_positives": cat_result.false_positives,
                "false_negatives": cat_result.false_negatives,
                "time_to_triage_seconds": cat_result.time_to_triage_seconds,
            }
        return {
            "dataset_name": result.dataset_name,
            "precision": result.precision,
            "recall": result.recall,
            "f1_score": result.f1_score,
            "time_to_triage_seconds": result.time_to_triage_seconds,
            "artefacts_expected": result.artefacts_expected,
            "artefacts_recovered": result.artefacts_recovered,
            "false_positives_count": result.false_positives,
            "false_negatives_count": result.false_negatives,
            "true_positives": list(self._last_true_positives),
            "false_positives": list(self._last_false_positives),
            "false_negatives": list(self._last_false_negatives),
            "per_category": category_breakdown,
            "thresholds": dict(self._thresholds),
            "pass": passed,
        }

    def _build_identifier_set(self, artefact_set: ArtefactSet) -> set[str]:
        """Build comparable identifiers from recovered artefacts.

        Uses the same normalisation logic as ``DFRWSHandler._normalise_identifier``.

        Args:
            artefact_set: Recovered artefact set.

        Returns:
            Set of normalised identifier strings.
        """
        identifiers: set[str] = set()
        for artefact in artefact_set.artefacts:
            key = self._artefact_key(artefact)
            if key:
                identifiers.add(key)
        return identifiers

    def _build_ground_truth_set(self, gt: GroundTruth) -> set[str]:
        """Extract normalised identifiers from ground truth.

        Args:
            gt: Loaded ground-truth model.

        Returns:
            Set of normalised identifier strings.
        """
        identifiers: set[str] = set()
        for entry in gt.artefacts:
            identifiers.add(self._ground_truth_key(entry))
        return identifiers

    def _artefact_key(self, artefact: Artefact) -> str:
        """Derive a DFRWS-normalised identifier for a recovered artefact."""
        raw = dict(artefact.raw_data or {})
        if artefact.source_path:
            raw.setdefault("source_path", artefact.source_path)
            raw.setdefault("path", artefact.source_path)
        raw.setdefault("identifier", artefact.artefact_id)
        return self._ground_truth_loader._dfrws._normalise_identifier(
            artefact.category.value,
            raw,
        )

    def _ground_truth_key(self, entry: GroundTruthArtefact) -> str:
        """Resolve a comparable identifier for a ground-truth entry."""
        identifier = str(entry.identifier or "").strip()
        category = entry.category.value
        if identifier.startswith(f"{category}::"):
            return identifier
        # Re-normalise from expected_data when identifier is a bare token.
        raw = dict(entry.expected_data or {})
        if identifier and "identifier" not in raw:
            raw["identifier"] = identifier
        normalised = self._ground_truth_loader._dfrws._normalise_identifier(
            category,
            raw,
        )
        if normalised and normalised != f"{category}::":
            return normalised
        if identifier:
            token = self._ground_truth_loader._dfrws._normalise_token(identifier)
            return f"{category}::{token}" if token else f"{category}::"
        return f"{category}::"
