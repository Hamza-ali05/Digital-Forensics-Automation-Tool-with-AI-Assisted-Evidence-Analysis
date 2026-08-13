"""Descriptive analysis of anonymised usability questionnaire responses."""

from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.models.evaluation import UsabilityResponse
from dfat.evaluation.usability.tobin_comparison import (
    TobinComparison,
    TobinComparisonResult,
)

# Two-tailed 95% critical values of Student's t for small df (df = n-1).
# For df >= 30 use the normal approximation z = 1.96.
_T_CRIT_975: dict[int, float] = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
}


class DimensionStats(BaseModel):
    """Descriptive statistics for one questionnaire dimension."""

    model_config = ConfigDict(frozen=False, validate_assignment=True)

    dimension: str
    mean: float
    median: float
    std_dev: float
    min_val: int
    max_val: int
    sample_size: int = Field(ge=0)
    confidence_interval_95: tuple[float, float]


class UsabilityEvaluationReport(BaseModel):
    """Comprehensive usability evaluation report (RQ5)."""

    model_config = ConfigDict(frozen=False, validate_assignment=True)

    total_responses: int = Field(ge=0)
    dimensions: dict[str, DimensionStats]
    usefulness_percentage: float
    tobin_comparison: TobinComparisonResult
    qualitative_feedback: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResponseAnalyzer:
    """Compute descriptive statistics for usability responses (RQ5)."""

    def __init__(self, responses: list[UsabilityResponse]) -> None:
        """Initialise the analyzer.

        Args:
            responses: Collected anonymised usability responses.
        """
        self._responses = list(responses)
        self._tobin = TobinComparison()

    def compute_mean_ratings(self) -> dict[str, float]:
        """Return mean ratings per dimension.

        Usefulness uses each respondent's average of Q1 and Q4 when available.

        Returns:
            Mapping of dimension → mean (0.0 when empty / unavailable).
        """
        return {
            name: (statistics.fmean(values) if values else 0.0)
            for name, values in self._dimension_series().items()
        }

    def compute_median_ratings(self) -> dict[str, float]:
        """Return median ratings per dimension."""
        return {
            name: (float(statistics.median(values)) if values else 0.0)
            for name, values in self._dimension_series().items()
        }

    def compute_std_dev(self) -> dict[str, float]:
        """Return sample standard deviation per dimension (0.0 when n < 2)."""
        result: dict[str, float] = {}
        for name, values in self._dimension_series().items():
            if len(values) >= 2:
                result[name] = float(statistics.stdev(values))
            else:
                result[name] = 0.0
        return result

    def compute_usefulness_percentage(self) -> float:
        """Return percentage of respondents where avg(Q1, Q4) ≥ 4.

        When raw Q1/Q4 are absent, falls back to ``usefulness_rating ≥ 4``.
        Directly comparable to Tobin et al. (2021) 74%.

        Returns:
            Percentage in ``[0.0, 100.0]``.
        """
        if not self._responses:
            return 0.0
        positive = sum(
            1
            for response in self._responses
            if self._usefulness_average(response) >= 4.0
        )
        return 100.0 * positive / len(self._responses)

    def compute_descriptive_statistics(self) -> dict[str, DimensionStats]:
        """Compute descriptive statistics per dimension.

        Returns:
            Mapping of dimension → ``DimensionStats`` including 95% CI.
        """
        return {
            name: self._describe_dimension(name, values)
            for name, values in self._dimension_series().items()
        }

    def generate_evaluation_report(self) -> UsabilityEvaluationReport:
        """Generate a comprehensive usability evaluation report.

        Returns:
            ``UsabilityEvaluationReport`` with Tobin comparison and feedback.
        """
        usefulness_pct = self.compute_usefulness_percentage()
        tobin = self._tobin.compare(
            tool_usefulness_pct=usefulness_pct,
            tool_sample_size=len(self._responses),
        )
        qualitative = [
            text
            for response in self._responses
            if (text := (response.free_text_feedback or "").strip())
        ]
        return UsabilityEvaluationReport(
            total_responses=len(self._responses),
            dimensions=self.compute_descriptive_statistics(),
            usefulness_percentage=usefulness_pct,
            tobin_comparison=tobin,
            qualitative_feedback=qualitative,
            generated_at=datetime.now(UTC),
        )

    def _dimension_series(self) -> dict[str, list[float]]:
        """Build per-dimension numeric series from responses."""
        usefulness = [self._usefulness_average(r) for r in self._responses]
        accuracy = [float(r.accuracy_rating) for r in self._responses]
        clarity = [float(r.clarity_rating) for r in self._responses]
        comparative = [
            float(r.comparative_rating)
            for r in self._responses
            if r.comparative_rating is not None
        ]
        return {
            "usefulness": usefulness,
            "accuracy": accuracy,
            "clarity": clarity,
            "comparative": comparative,
        }

    @staticmethod
    def _usefulness_average(response: UsabilityResponse) -> float:
        """Return avg(Q1, Q4) when present, else aggregated usefulness rating."""
        if response.q1_rating is not None and response.q4_rating is not None:
            return (float(response.q1_rating) + float(response.q4_rating)) / 2.0
        return float(response.usefulness_rating)

    @classmethod
    def _describe_dimension(
        cls,
        dimension: str,
        values: Sequence[float],
    ) -> DimensionStats:
        """Build ``DimensionStats`` for one dimension series."""
        sample = list(values)
        n = len(sample)
        if n == 0:
            return DimensionStats(
                dimension=dimension,
                mean=0.0,
                median=0.0,
                std_dev=0.0,
                min_val=0,
                max_val=0,
                sample_size=0,
                confidence_interval_95=(0.0, 0.0),
            )
        mean = float(statistics.fmean(sample))
        median = float(statistics.median(sample))
        std_dev = float(statistics.stdev(sample)) if n >= 2 else 0.0
        return DimensionStats(
            dimension=dimension,
            mean=mean,
            median=median,
            std_dev=std_dev,
            min_val=int(round(min(sample))),
            max_val=int(round(max(sample))),
            sample_size=n,
            confidence_interval_95=cls._confidence_interval_95(sample),
        )

    @staticmethod
    def _confidence_interval_95(values: Sequence[float]) -> tuple[float, float]:
        """Compute a two-sided 95% CI using Student's t for small samples.

        Args:
            values: Numeric sample (length ≥ 1).

        Returns:
            ``(lower, upper)``. For ``n == 1`` returns ``(mean, mean)``.
        """
        n = len(values)
        mean = float(statistics.fmean(values))
        if n < 2:
            return (mean, mean)
        std_err = float(statistics.stdev(values)) / math.sqrt(n)
        df = n - 1
        t_crit = _T_CRIT_975.get(df, 1.96)
        margin = t_crit * std_err
        return (mean - margin, mean + margin)
