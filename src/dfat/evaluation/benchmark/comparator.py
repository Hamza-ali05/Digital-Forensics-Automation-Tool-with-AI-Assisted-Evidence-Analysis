"""Automated comparison of recovered artefacts against ground truth."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from dfat.core.enums import PipelineStage
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evaluation import BenchmarkResult
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

_DEFAULT_THRESHOLDS: dict[str, float] = {
    "precision_min": 0.0,
    "recall_min": 0.0,
    "f1_min": 0.0,
}


class BenchmarkComparator:
    """Compare recovered artefacts to ground truth and compute metrics."""

    def __init__(
        self,
        metrics_calculator: MetricsCalculator,
        audit_logger: ForensicAuditLogger,
        thresholds: Optional[dict[str, float]] = None,
    ) -> None:
        """Initialise the comparator.

        Args:
            metrics_calculator: Metrics computation service.
            audit_logger: Forensic audit logger.
            thresholds: Optional pass/fail metric thresholds.
        """
        self._metrics = metrics_calculator
        self._audit_logger = audit_logger
        self._thresholds = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._last_false_positives: list[str] = []
        self._last_false_negatives: list[str] = []

    def compare(
        self,
        recovered: ArtefactSet,
        ground_truth: dict[str, Any],
        pipeline_start: datetime,
        pipeline_end: datetime,
    ) -> BenchmarkResult:
        """Compare recovered artefacts against ground truth.

        Args:
            recovered: Pipeline-recovered artefact set.
            ground_truth: Loaded ground-truth mapping.
            pipeline_start: Pipeline start timestamp.
            pipeline_end: Pipeline end timestamp.

        Returns:
            Benchmark result with precision, recall, F1, and TTT.
        """
        recovered_ids = self._build_identifier_set(recovered)
        expected_ids = self._build_ground_truth_set(ground_truth)

        true_positives_set = recovered_ids & expected_ids
        false_positives_set = recovered_ids - expected_ids
        false_negatives_set = expected_ids - recovered_ids

        self._last_false_positives = sorted(false_positives_set)
        self._last_false_negatives = sorted(false_negatives_set)

        dataset_name = str(ground_truth.get("dataset_name", "unknown"))
        result = self._metrics.compute_all(
            true_positives=len(true_positives_set),
            false_positives=len(false_positives_set),
            false_negatives=len(false_negatives_set),
            start_time=pipeline_start,
            end_time=pipeline_end,
            dataset_name=dataset_name,
        )

        self._audit_logger.log_action(
            stage=PipelineStage.EVALUATION,
            action="BENCHMARK_EVALUATION_COMPLETED",
            evidence_id=recovered.evidence_id,
            details={
                "dataset_name": dataset_name,
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

    def _build_identifier_set(self, artefact_set: ArtefactSet) -> set[str]:
        """Build comparable identifiers from recovered artefacts.

        Args:
            artefact_set: Recovered artefact set.

        Returns:
            Set of ``category::identifier`` strings.
        """
        identifiers: set[str] = set()
        for artefact in artefact_set.artefacts:
            identifiers.add(self._artefact_key(artefact))
        return identifiers

    def _build_ground_truth_set(self, ground_truth: dict[str, Any]) -> set[str]:
        """Build comparable identifiers from ground-truth entries.

        Args:
            ground_truth: Loaded ground-truth mapping.

        Returns:
            Set of ``category::identifier`` strings.
        """
        identifiers: set[str] = set()
        for entry in ground_truth.get("artefacts", []):
            if not isinstance(entry, dict):
                continue
            category = str(entry.get("category", "")).strip().lower()
            identifier = self._normalise_identifier(str(entry.get("identifier", "")))
            if category and identifier:
                identifiers.add(f"{category}::{identifier}")
        return identifiers

    def generate_comparison_report(self, result: BenchmarkResult) -> dict[str, Any]:
        """Build a human-readable comparison report.

        Args:
            result: Computed benchmark metrics.

        Returns:
            Comparison dictionary including metrics, FP/FN lists, and pass/fail.
        """
        passed = (
            result.precision >= self._thresholds["precision_min"]
            and result.recall >= self._thresholds["recall_min"]
            and result.f1_score >= self._thresholds["f1_min"]
        )
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
            "false_positives": list(self._last_false_positives),
            "false_negatives": list(self._last_false_negatives),
            "thresholds": dict(self._thresholds),
            "pass": passed,
        }

    @staticmethod
    def _artefact_key(artefact: Artefact) -> str:
        """Derive a comparable identifier for a recovered artefact."""
        raw = artefact.raw_data
        candidate = (
            raw.get("identifier")
            or raw.get("path")
            or raw.get("key_path")
            or raw.get("url")
            or raw.get("name")
            or raw.get("pid")
            or artefact.source_path
            or artefact.artefact_id
        )
        identifier = BenchmarkComparator._normalise_identifier(str(candidate))
        return f"{artefact.category.value}::{identifier}"

    @staticmethod
    def _normalise_identifier(value: str) -> str:
        """Normalise an identifier for set comparison."""
        return " ".join(value.strip().lower().replace("\\", "/").split())
