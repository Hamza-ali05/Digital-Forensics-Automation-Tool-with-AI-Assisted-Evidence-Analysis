"""Precision, recall, F1, and time-to-triage metric calculations."""

from __future__ import annotations

from datetime import datetime

from dfat.core.models.evaluation import BenchmarkResult


class MetricsCalculator:
    """Compute standard information-retrieval metrics for benchmark evaluation."""

    def compute_precision(self, true_positives: int, false_positives: int) -> float:
        """Compute precision = TP / (TP + FP).

        Args:
            true_positives: True positive count.
            false_positives: False positive count.

        Returns:
            Precision in ``[0.0, 1.0]``, or ``0.0`` when the denominator is zero.
        """
        denominator = true_positives + false_positives
        if denominator == 0:
            return 0.0
        return true_positives / denominator

    def compute_recall(self, true_positives: int, false_negatives: int) -> float:
        """Compute recall = TP / (TP + FN).

        Args:
            true_positives: True positive count.
            false_negatives: False negative count.

        Returns:
            Recall in ``[0.0, 1.0]``, or ``0.0`` when the denominator is zero.
        """
        denominator = true_positives + false_negatives
        if denominator == 0:
            return 0.0
        return true_positives / denominator

    def compute_f1(self, precision: float, recall: float) -> float:
        """Compute F1 = 2 * (P * R) / (P + R).

        Args:
            precision: Precision score.
            recall: Recall score.

        Returns:
            F1 score, or ``0.0`` when the denominator is zero.
        """
        denominator = precision + recall
        if denominator == 0:
            return 0.0
        return 2.0 * (precision * recall) / denominator

    def compute_time_to_triage(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> float:
        """Compute elapsed triage time in seconds.

        Args:
            start_time: Pipeline start timestamp.
            end_time: Pipeline end timestamp.

        Returns:
            Non-negative elapsed seconds.
        """
        return max(0.0, (end_time - start_time).total_seconds())

    def compute_all(
        self,
        true_positives: int,
        false_positives: int,
        false_negatives: int,
        start_time: datetime,
        end_time: datetime,
        dataset_name: str,
    ) -> BenchmarkResult:
        """Compute all benchmark metrics and return a ``BenchmarkResult``.

        Args:
            true_positives: True positive count.
            false_positives: False positive count.
            false_negatives: False negative count.
            start_time: Pipeline start timestamp.
            end_time: Pipeline end timestamp.
            dataset_name: Ground-truth dataset name.

        Returns:
            Populated benchmark result model.
        """
        precision = self.compute_precision(true_positives, false_positives)
        recall = self.compute_recall(true_positives, false_negatives)
        f1_score = self.compute_f1(precision, recall)
        ttt = self.compute_time_to_triage(start_time, end_time)
        artefacts_expected = true_positives + false_negatives
        artefacts_recovered = true_positives + false_positives
        return BenchmarkResult(
            dataset_name=dataset_name,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            time_to_triage_seconds=ttt,
            artefacts_expected=artefacts_expected,
            artefacts_recovered=artefacts_recovered,
            false_positives=false_positives,
            false_negatives=false_negatives,
        )
