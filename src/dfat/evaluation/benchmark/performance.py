"""Time-to-triage and multi-run performance analytics for benchmark evaluation."""

from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.exceptions import MetricsCalculationError
from dfat.core.models.evaluation import BenchmarkResult
from dfat.database.repositories.evaluation_repo import SQLAlchemyBenchmarkRepository


class TimeStats(BaseModel):
    """Descriptive statistics for a numeric sample (time or score series).

    Attributes:
        mean: Arithmetic mean.
        median: Median value.
        std_dev: Sample standard deviation (``0.0`` when ``n < 2``).
        min_val: Minimum observed value.
        max_val: Maximum observed value.
        p95: 95th percentile.
        p99: 99th percentile.
        sample_count: Number of observations.
    """

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
    )

    mean: float
    median: float
    std_dev: float
    min_val: float
    max_val: float
    p95: float
    p99: float
    sample_count: int = Field(ge=0)


class SpeedupResult(BaseModel):
    """Comparison of tool time-to-triage against a baseline tool.

    Attributes:
        tool_ttt: DFAT (or candidate tool) time-to-triage in seconds.
        baseline_ttt: Baseline tool time-to-triage in seconds.
        speedup_factor: ``baseline_ttt / tool_ttt`` (>1 means faster than baseline).
        percentage_improvement: Relative improvement vs baseline (percent).
    """

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
    )

    tool_ttt: float
    baseline_ttt: float
    speedup_factor: float
    percentage_improvement: float


class PerformanceReport(BaseModel):
    """Aggregated performance analytics across benchmark runs.

    Attributes:
        dataset_name: Dataset the runs belong to.
        run_count: Number of runs analysed.
        time_stats: Time-to-triage statistics.
        precision_stats: Precision score statistics.
        recall_stats: Recall score statistics.
        f1_stats: F1 score statistics.
        baseline_comparison: Optional speedup vs an external baseline TTT.
        generated_at: UTC report generation timestamp.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    dataset_name: str
    run_count: int = Field(ge=0)
    time_stats: TimeStats
    precision_stats: TimeStats
    recall_stats: TimeStats
    f1_stats: TimeStats
    baseline_comparison: Optional[SpeedupResult] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PerformanceAnalyzer:
    """Measure and analyse pipeline performance across multiple benchmark runs."""

    def __init__(self, benchmark_repo: SQLAlchemyBenchmarkRepository) -> None:
        """Initialise the performance analyzer.

        Args:
            benchmark_repo: Persistence repository for historical benchmark results.
        """
        self._benchmark_repo = benchmark_repo

    def compute_time_statistics(self, results: list[BenchmarkResult]) -> TimeStats:
        """Compute time-to-triage statistics across multiple benchmark runs.

        Args:
            results: Benchmark results to summarise.

        Returns:
            Mean, median, std-dev, min/max, p95/p99, and sample count.

        Raises:
            MetricsCalculationError: If ``results`` is empty.
        """
        values = [float(result.time_to_triage_seconds) for result in results]
        return self._compute_stats(values)

    def compare_against_baseline(
        self,
        tool_ttt: float,
        baseline_ttt: float,
    ) -> SpeedupResult:
        """Compare tool time-to-triage against a baseline.

        Args:
            tool_ttt: Candidate tool triage duration in seconds.
            baseline_ttt: Baseline tool triage duration in seconds.

        Returns:
            Speedup factor and percentage improvement.

        Raises:
            MetricsCalculationError: If either duration is non-positive.
        """
        tool = float(tool_ttt)
        baseline = float(baseline_ttt)
        if tool <= 0.0:
            raise MetricsCalculationError(
                "tool_ttt must be positive for speedup comparison",
                context={"tool_ttt": tool, "baseline_ttt": baseline},
            )
        if baseline <= 0.0:
            raise MetricsCalculationError(
                "baseline_ttt must be positive for speedup comparison",
                context={"tool_ttt": tool, "baseline_ttt": baseline},
            )
        speedup = baseline / tool
        percentage_improvement = ((baseline - tool) / baseline) * 100.0
        return SpeedupResult(
            tool_ttt=tool,
            baseline_ttt=baseline,
            speedup_factor=speedup,
            percentage_improvement=percentage_improvement,
        )

    async def get_historical_results(self, dataset_name: str) -> list[BenchmarkResult]:
        """Load all stored benchmark results for a dataset.

        Args:
            dataset_name: Ground-truth dataset name.

        Returns:
            Historical ``BenchmarkResult`` rows for the dataset.
        """
        return await self._benchmark_repo.get_by_dataset(dataset_name)

    def generate_performance_report(
        self,
        results: list[BenchmarkResult],
        baseline_ttt: Optional[float] = None,
    ) -> PerformanceReport:
        """Build a performance report with time/score stats and optional baseline.

        Includes trend-oriented extrema via min/max/mean in ``time_stats`` and
        per-metric distributions for precision, recall, and F1.

        Args:
            results: Benchmark runs to analyse (single-run is supported).
            baseline_ttt: Optional baseline tool TTT for speedup comparison.
                When set, the mean tool TTT is compared against this baseline.

        Returns:
            Populated ``PerformanceReport``.

        Raises:
            MetricsCalculationError: If ``results`` is empty.
        """
        if not results:
            raise MetricsCalculationError(
                "performance report requires at least one benchmark result",
                context={"run_count": 0},
            )

        time_stats = self.compute_time_statistics(results)
        precision_stats = self._compute_stats([float(r.precision) for r in results])
        recall_stats = self._compute_stats([float(r.recall) for r in results])
        f1_stats = self._compute_stats([float(r.f1_score) for r in results])

        baseline_comparison: Optional[SpeedupResult] = None
        if baseline_ttt is not None:
            baseline_comparison = self.compare_against_baseline(
                tool_ttt=time_stats.mean,
                baseline_ttt=float(baseline_ttt),
            )

        dataset_name = results[0].dataset_name
        return PerformanceReport(
            dataset_name=dataset_name,
            run_count=len(results),
            time_stats=time_stats,
            precision_stats=precision_stats,
            recall_stats=recall_stats,
            f1_stats=f1_stats,
            baseline_comparison=baseline_comparison,
            generated_at=datetime.now(UTC),
        )

    def _compute_stats(self, values: Sequence[float]) -> TimeStats:
        """Compute descriptive statistics for a numeric series.

        Args:
            values: Sample values.

        Returns:
            ``TimeStats`` for the sample.

        Raises:
            MetricsCalculationError: If ``values`` is empty.
        """
        if not values:
            raise MetricsCalculationError(
                "statistics require at least one sample",
                context={"sample_count": 0},
            )

        ordered = sorted(float(v) for v in values)
        n = len(ordered)
        mean = float(statistics.fmean(ordered))
        median = float(statistics.median(ordered))
        std_dev = float(statistics.stdev(ordered)) if n >= 2 else 0.0
        return TimeStats(
            mean=mean,
            median=median,
            std_dev=std_dev,
            min_val=float(ordered[0]),
            max_val=float(ordered[-1]),
            p95=self._percentile(ordered, 95.0),
            p99=self._percentile(ordered, 99.0),
            sample_count=n,
        )

    @staticmethod
    def _percentile(ordered: Sequence[float], percentile: float) -> float:
        """Linear-interpolation percentile for a sorted non-empty sample.

        Args:
            ordered: Ascending-sorted values (length ≥ 1).
            percentile: Percentile in ``[0, 100]``.

        Returns:
            Interpolated percentile value. Single-sample series return that value.
        """
        if len(ordered) == 1:
            return float(ordered[0])
        rank = (percentile / 100.0) * (len(ordered) - 1)
        lower = int(math.floor(rank))
        upper = int(math.ceil(rank))
        if lower == upper:
            return float(ordered[lower])
        weight = rank - lower
        return float(ordered[lower]) * (1.0 - weight) + float(ordered[upper]) * weight
