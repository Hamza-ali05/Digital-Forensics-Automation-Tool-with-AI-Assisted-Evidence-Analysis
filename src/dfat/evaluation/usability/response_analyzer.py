"""Descriptive analysis of anonymised usability questionnaire responses."""

from __future__ import annotations

import statistics
from typing import Any

from dfat.core.models.evaluation import UsabilityResponse

_TOBIN_USEFULNESS_BENCHMARK = 74.0


class ResponseAnalyzer:
    """Compute descriptive statistics for usability responses (RQ5)."""

    def __init__(self, responses: list[UsabilityResponse]) -> None:
        """Initialise the analyzer.

        Args:
            responses: Collected anonymised usability responses.
        """
        self._responses = list(responses)

    def compute_mean_ratings(self) -> dict[str, float]:
        """Return mean usefulness, accuracy, and clarity ratings.

        Returns:
            Mapping of dimension name to mean rating (0.0 when empty).
        """
        if not self._responses:
            return {"usefulness": 0.0, "accuracy": 0.0, "clarity": 0.0}
        return {
            "usefulness": statistics.fmean(r.usefulness_rating for r in self._responses),
            "accuracy": statistics.fmean(r.accuracy_rating for r in self._responses),
            "clarity": statistics.fmean(r.clarity_rating for r in self._responses),
        }

    def compute_usefulness_percentage(self) -> float:
        """Return percentage of respondents with usefulness ≥ 4.

        This metric is directly comparable to Tobin et al. (2021) (74%).

        Returns:
            Percentage in ``[0.0, 100.0]``.
        """
        if not self._responses:
            return 0.0
        positive = sum(1 for response in self._responses if response.usefulness_rating >= 4)
        return 100.0 * positive / len(self._responses)

    def compute_descriptive_statistics(self) -> dict[str, Any]:
        """Compute descriptive statistics per Likert dimension.

        Returns:
            Mapping of dimension → {mean, median, std_dev, min, max, n}.
        """
        dimensions = {
            "usefulness": [r.usefulness_rating for r in self._responses],
            "accuracy": [r.accuracy_rating for r in self._responses],
            "clarity": [r.clarity_rating for r in self._responses],
        }
        report: dict[str, Any] = {}
        for name, values in dimensions.items():
            report[name] = self._describe(values)
        return report

    def generate_evaluation_report(self) -> dict[str, Any]:
        """Generate a comprehensive usability evaluation report.

        Returns:
            Report including statistics, Tobin et al. comparison, and n.
        """
        usefulness_pct = self.compute_usefulness_percentage()
        return {
            "participant_count": len(self._responses),
            "mean_ratings": self.compute_mean_ratings(),
            "descriptive_statistics": self.compute_descriptive_statistics(),
            "usefulness_percentage_ge_4": usefulness_pct,
            "tobin_et_al_2021_benchmark_percent": _TOBIN_USEFULNESS_BENCHMARK,
            "comparison_to_tobin": {
                "benchmark_percent": _TOBIN_USEFULNESS_BENCHMARK,
                "observed_percent": usefulness_pct,
                "delta_percent": usefulness_pct - _TOBIN_USEFULNESS_BENCHMARK,
                "meets_or_exceeds_benchmark": usefulness_pct >= _TOBIN_USEFULNESS_BENCHMARK,
            },
        }

    @staticmethod
    def _describe(values: list[int]) -> dict[str, Any]:
        """Describe a numeric sample."""
        if not values:
            return {
                "mean": 0.0,
                "median": 0.0,
                "std_dev": 0.0,
                "min": 0,
                "max": 0,
                "n": 0,
            }
        return {
            "mean": statistics.fmean(values),
            "median": float(statistics.median(values)),
            "std_dev": float(statistics.pstdev(values)) if len(values) > 1 else 0.0,
            "min": min(values),
            "max": max(values),
            "n": len(values),
        }
