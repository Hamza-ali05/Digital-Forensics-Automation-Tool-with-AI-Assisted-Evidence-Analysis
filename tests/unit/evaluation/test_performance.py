"""Unit tests for performance analytics (Prompt 6.14)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from dfat.core.exceptions import MetricsCalculationError
from dfat.core.models.evaluation import BenchmarkResult
from dfat.evaluation.benchmark.performance import PerformanceAnalyzer


def _result(
    *,
    ttt: float,
    precision: float = 0.8,
    recall: float = 0.7,
    f1: float = 0.75,
    dataset_name: str = "unit_gt",
) -> BenchmarkResult:
    """Build a minimal BenchmarkResult for tests."""
    return BenchmarkResult(
        dataset_name=dataset_name,
        precision=precision,
        recall=recall,
        f1_score=f1,
        time_to_triage_seconds=ttt,
        artefacts_expected=10,
        artefacts_recovered=8,
        false_positives=2,
        false_negatives=2,
        evaluated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def test_compute_time_statistics_mean_median_std_dev() -> None:
    """Verify mean/median/std_dev for a known TTT series."""
    analyzer = PerformanceAnalyzer(AsyncMock())
    results = [_result(ttt=v) for v in (10.0, 20.0, 30.0, 40.0, 50.0)]
    stats = analyzer.compute_time_statistics(results)
    assert stats.sample_count == 5
    assert stats.mean == 30.0
    assert stats.median == 30.0
    assert abs(stats.std_dev - 15.811388300841896) < 1e-9
    assert stats.min_val == 10.0
    assert stats.max_val == 50.0
    assert stats.p95 == pytest.approx(48.0)
    assert stats.p99 == pytest.approx(49.6)


def test_compute_time_statistics_single_run() -> None:
    """Verify single-run series is handled without division errors."""
    analyzer = PerformanceAnalyzer(AsyncMock())
    stats = analyzer.compute_time_statistics([_result(ttt=12.5)])
    assert stats.sample_count == 1
    assert stats.mean == 12.5
    assert stats.median == 12.5
    assert stats.std_dev == 0.0
    assert stats.min_val == 12.5
    assert stats.max_val == 12.5
    assert stats.p95 == 12.5
    assert stats.p99 == 12.5


def test_compare_against_baseline_speedup() -> None:
    """Verify speedup = baseline / tool and percentage improvement."""
    analyzer = PerformanceAnalyzer(AsyncMock())
    result = analyzer.compare_against_baseline(tool_ttt=50.0, baseline_ttt=100.0)
    assert result.tool_ttt == 50.0
    assert result.baseline_ttt == 100.0
    assert result.speedup_factor == 2.0
    assert result.percentage_improvement == 50.0


def test_compare_against_baseline_rejects_non_positive() -> None:
    """Verify non-positive durations raise MetricsCalculationError."""
    analyzer = PerformanceAnalyzer(AsyncMock())
    with pytest.raises(MetricsCalculationError):
        analyzer.compare_against_baseline(tool_ttt=0.0, baseline_ttt=100.0)
    with pytest.raises(MetricsCalculationError):
        analyzer.compare_against_baseline(tool_ttt=10.0, baseline_ttt=-1.0)


@pytest.mark.asyncio
async def test_get_historical_results_loads_from_database() -> None:
    """Verify historical results are loaded via the benchmark repository."""
    repo = AsyncMock()
    expected = [_result(ttt=11.0), _result(ttt=22.0)]
    repo.get_by_dataset.return_value = expected
    analyzer = PerformanceAnalyzer(repo)

    loaded = await analyzer.get_historical_results("unit_gt")

    assert loaded == expected
    repo.get_by_dataset.assert_awaited_once_with("unit_gt")


def test_generate_performance_report_with_baseline() -> None:
    """Verify report includes time/score stats and baseline comparison."""
    analyzer = PerformanceAnalyzer(AsyncMock())
    results = [
        _result(ttt=40.0, precision=0.8, recall=0.6, f1=0.7),
        _result(ttt=60.0, precision=1.0, recall=0.8, f1=0.9),
    ]
    report = analyzer.generate_performance_report(results, baseline_ttt=100.0)

    assert report.dataset_name == "unit_gt"
    assert report.run_count == 2
    assert report.time_stats.mean == 50.0
    assert report.precision_stats.mean == 0.9
    assert report.recall_stats.mean == 0.7
    assert report.f1_stats.mean == 0.8
    assert report.baseline_comparison is not None
    assert report.baseline_comparison.speedup_factor == 2.0
    assert report.baseline_comparison.percentage_improvement == 50.0


def test_generate_performance_report_rejects_empty() -> None:
    """Verify empty result lists raise MetricsCalculationError."""
    analyzer = PerformanceAnalyzer(AsyncMock())
    with pytest.raises(MetricsCalculationError):
        analyzer.generate_performance_report([])
