"""Unit tests for metrics visualisation helpers (Prompt 6.15)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dfat.core.models.evaluation import BenchmarkResult
from dfat.evaluation.benchmark.visualisation import MetricsVisualiser


def _result(
    *,
    dataset: str,
    precision: float,
    recall: float,
    f1: float,
    ttt: float,
    evaluated_at: datetime,
) -> BenchmarkResult:
    """Build a BenchmarkResult for visualisation tests."""
    return BenchmarkResult(
        dataset_name=dataset,
        precision=precision,
        recall=recall,
        f1_score=f1,
        time_to_triage_seconds=ttt,
        artefacts_expected=10,
        artefacts_recovered=8,
        false_positives=1,
        false_negatives=2,
        evaluated_at=evaluated_at,
    )


def test_prepare_precision_recall_data_is_charting_ready() -> None:
    """Verify PR series includes aligned labels and value arrays."""
    results = [
        _result(
            dataset="gt",
            precision=0.8,
            recall=0.7,
            f1=0.75,
            ttt=10.0,
            evaluated_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        _result(
            dataset="gt",
            precision=0.9,
            recall=0.85,
            f1=0.87,
            ttt=12.0,
            evaluated_at=datetime(2024, 1, 2, tzinfo=UTC),
        ),
    ]
    payload = MetricsVisualiser().prepare_precision_recall_data(results)
    assert payload["labels"] == ["gt#1", "gt#2"]
    assert payload["precision_values"] == [0.8, 0.9]
    assert payload["recall_values"] == [0.7, 0.85]


def test_prepare_category_breakdown_from_benchmark_results() -> None:
    """Verify category breakdown arrays align with sorted categories."""
    per_category = {
        "browser_history": _result(
            dataset="gt:browser_history",
            precision=0.5,
            recall=0.5,
            f1=0.5,
            ttt=1.0,
            evaluated_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        "running_process": _result(
            dataset="gt:running_process",
            precision=1.0,
            recall=1.0,
            f1=1.0,
            ttt=1.0,
            evaluated_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
    }
    payload = MetricsVisualiser().prepare_category_breakdown(per_category)
    assert payload["categories"] == ["browser_history", "running_process"]
    assert payload["precision"] == [0.5, 1.0]
    assert payload["recall"] == [0.5, 1.0]
    assert payload["f1"] == [0.5, 1.0]


def test_prepare_timeline_comparison_orders_by_evaluated_at() -> None:
    """Verify TTT timeline is sorted chronologically."""
    later = datetime(2024, 1, 2, tzinfo=UTC)
    earlier = later - timedelta(days=1)
    results = [
        _result(
            dataset="gt",
            precision=0.9,
            recall=0.9,
            f1=0.9,
            ttt=20.0,
            evaluated_at=later,
        ),
        _result(
            dataset="gt",
            precision=0.8,
            recall=0.8,
            f1=0.8,
            ttt=10.0,
            evaluated_at=earlier,
        ),
    ]
    payload = MetricsVisualiser().prepare_timeline_comparison(results)
    assert payload["timestamps"] == [earlier.isoformat(), later.isoformat()]
    assert payload["ttt_values"] == [10.0, 20.0]
    assert payload["labels"] == ["gt#1", "gt#2"]
