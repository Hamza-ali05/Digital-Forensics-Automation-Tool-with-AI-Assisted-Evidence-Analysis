"""Charting-ready data structures for benchmark metrics visualisation."""

from __future__ import annotations

from typing import Any, Mapping

from dfat.core.models.evaluation import BenchmarkResult


class MetricsVisualiser:
    """Prepare benchmark metric series for front-end / report charts."""

    def prepare_precision_recall_data(
        self,
        results: list[BenchmarkResult],
    ) -> dict[str, Any]:
        """Structure precision/recall series for charting.

        Args:
            results: Benchmark runs to visualise.

        Returns:
            Mapping with ``labels``, ``precision_values``, and ``recall_values``.
        """
        labels: list[str] = []
        precision_values: list[float] = []
        recall_values: list[float] = []
        for index, result in enumerate(results):
            labels.append(
                f"{result.dataset_name}#{index + 1}"
                if result.dataset_name
                else result.benchmark_id
            )
            precision_values.append(float(result.precision))
            recall_values.append(float(result.recall))
        return {
            "labels": labels,
            "precision_values": precision_values,
            "recall_values": recall_values,
        }

    def prepare_category_breakdown(
        self,
        per_category: Mapping[str, BenchmarkResult | Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Structure per-category metrics for a grouped bar chart.

        Args:
            per_category: Category → ``BenchmarkResult`` or metric mapping.

        Returns:
            Mapping with ``categories``, ``precision``, ``recall``, and ``f1``.
        """
        categories = sorted(per_category.keys(), key=str)
        precision: list[float] = []
        recall: list[float] = []
        f1: list[float] = []
        for category in categories:
            entry = per_category[category]
            if isinstance(entry, BenchmarkResult):
                precision.append(float(entry.precision))
                recall.append(float(entry.recall))
                f1.append(float(entry.f1_score))
            else:
                precision.append(float(entry.get("precision", 0.0)))
                recall.append(float(entry.get("recall", 0.0)))
                f1.append(float(entry.get("f1_score", entry.get("f1", 0.0))))
        return {
            "categories": categories,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    def prepare_timeline_comparison(
        self,
        results: list[BenchmarkResult],
    ) -> dict[str, Any]:
        """Structure time-to-triage values over time for trend analysis.

        Args:
            results: Benchmark runs ordered or unordered (sorted by evaluated_at).

        Returns:
            Mapping with ``timestamps``, ``labels``, and ``ttt_values``.
        """
        ordered = sorted(results, key=lambda item: item.evaluated_at)
        timestamps: list[str] = []
        labels: list[str] = []
        ttt_values: list[float] = []
        for index, result in enumerate(ordered):
            timestamps.append(result.evaluated_at.isoformat())
            labels.append(f"{result.dataset_name}#{index + 1}")
            ttt_values.append(float(result.time_to_triage_seconds))
        return {
            "timestamps": timestamps,
            "labels": labels,
            "ttt_values": ttt_values,
        }
