"""Precision, recall, F1, accuracy, and time-to-triage metric calculations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Mapping

from dfat.core.exceptions import MetricsCalculationError
from dfat.core.models.evaluation import BenchmarkResult


class MetricsCalculator:
    """Compute standard information-retrieval metrics for benchmark evaluation."""

    def compute_precision(self, tp: int, fp: int) -> float:
        """Compute precision = TP / (TP + FP).

        Args:
            tp: True positive count.
            fp: False positive count.

        Returns:
            Precision in ``[0.0, 1.0]``, or ``0.0`` when the denominator is zero.
        """
        denominator = int(tp) + int(fp)
        if denominator == 0:
            return 0.0
        return float(tp) / float(denominator)

    def compute_recall(self, tp: int, fn: int) -> float:
        """Compute recall = TP / (TP + FN).

        Args:
            tp: True positive count.
            fn: False negative count.

        Returns:
            Recall in ``[0.0, 1.0]``, or ``0.0`` when the denominator is zero.
        """
        denominator = int(tp) + int(fn)
        if denominator == 0:
            return 0.0
        return float(tp) / float(denominator)

    def compute_f1(self, precision: float, recall: float) -> float:
        """Compute F1 = 2 * P * R / (P + R).

        Args:
            precision: Precision score.
            recall: Recall score.

        Returns:
            F1 score, or ``0.0`` when the denominator is zero.
        """
        denominator = float(precision) + float(recall)
        if denominator == 0:
            return 0.0
        return 2.0 * float(precision) * float(recall) / denominator

    def compute_accuracy(self, tp: int, fp: int, fn: int) -> float:
        """Compute accuracy = TP / (TP + FP + FN).

        Args:
            tp: True positive count.
            fp: False positive count.
            fn: False negative count.

        Returns:
            Accuracy in ``[0.0, 1.0]``, or ``0.0`` when the denominator is zero.
        """
        denominator = int(tp) + int(fp) + int(fn)
        if denominator == 0:
            return 0.0
        return float(tp) / float(denominator)

    def compute_time_to_triage(self, start: datetime, end: datetime) -> float:
        """Compute elapsed triage time in seconds.

        Args:
            start: Pipeline start timestamp.
            end: Pipeline end timestamp.

        Returns:
            Positive elapsed seconds.

        Raises:
            MetricsCalculationError: If ``end`` is not strictly after ``start``.
        """
        elapsed = (end - start).total_seconds()
        if elapsed <= 0:
            raise MetricsCalculationError(
                "time_to_triage requires end > start (non-positive duration)",
                context={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "elapsed_seconds": elapsed,
                },
            )
        return float(elapsed)

    def compute_all(
        self,
        tp: int,
        fp: int,
        fn: int,
        start: datetime,
        end: datetime,
        dataset_name: str,
        artefacts_expected: int,
        artefacts_recovered: int,
    ) -> BenchmarkResult:
        """Compute all benchmark metrics and return a ``BenchmarkResult``.

        Args:
            tp: True positive count.
            fp: False positive count.
            fn: False negative count.
            start: Pipeline start timestamp.
            end: Pipeline end timestamp.
            dataset_name: Ground-truth dataset name.
            artefacts_expected: Expected relevant artefact count.
            artefacts_recovered: Recovered artefact count.

        Returns:
            Populated benchmark result model including ``evaluated_at``.
        """
        precision = self.compute_precision(tp, fp)
        recall = self.compute_recall(tp, fn)
        f1_score = self.compute_f1(precision, recall)
        ttt = self.compute_time_to_triage(start, end)
        return BenchmarkResult(
            dataset_name=dataset_name,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            time_to_triage_seconds=ttt,
            artefacts_expected=int(artefacts_expected),
            artefacts_recovered=int(artefacts_recovered),
            false_positives=int(fp),
            false_negatives=int(fn),
            evaluated_at=datetime.now(UTC),
        )

    def compute_per_category(
        self,
        tp_by_cat: Mapping[str, int],
        fp_by_cat: Mapping[str, int],
        fn_by_cat: Mapping[str, int],
    ) -> dict[str, dict[str, float]]:
        """Compute precision/recall/F1 independently per artefact category.

        Args:
            tp_by_cat: True positives keyed by category name.
            fp_by_cat: False positives keyed by category name.
            fn_by_cat: False negatives keyed by category name.

        Returns:
            Mapping of category → ``{precision, recall, f1, accuracy}``.
        """
        categories = sorted(
            set(tp_by_cat) | set(fp_by_cat) | set(fn_by_cat),
            key=str,
        )
        results: dict[str, dict[str, float]] = {}
        for category in categories:
            tp = int(tp_by_cat.get(category, 0))
            fp = int(fp_by_cat.get(category, 0))
            fn = int(fn_by_cat.get(category, 0))
            precision = self.compute_precision(tp, fp)
            recall = self.compute_recall(tp, fn)
            results[str(category)] = {
                "precision": precision,
                "recall": recall,
                "f1": self.compute_f1(precision, recall),
                "accuracy": self.compute_accuracy(tp, fp, fn),
            }
        return results
