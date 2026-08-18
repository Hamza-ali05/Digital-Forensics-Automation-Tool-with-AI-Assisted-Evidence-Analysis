"""Extended zero, perfect, and sparse-category metric tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dfat.evaluation.benchmark.metrics import MetricsCalculator


def test_all_zero_counts_produce_zero_metrics() -> None:
    # Arrange
    calc = MetricsCalculator()

    # Act / Assert
    assert calc.compute_precision(0, 0) == 0.0
    assert calc.compute_recall(0, 0) == 0.0
    assert calc.compute_f1(0.0, 0.0) == 0.0


def test_perfect_true_positive_only_metrics_are_one() -> None:
    # Arrange
    calc = MetricsCalculator()
    precision = calc.compute_precision(1, 0)
    recall = calc.compute_recall(1, 0)

    # Act / Assert
    assert precision == recall == 1.0
    assert calc.compute_f1(precision, recall) == 1.0


def test_compute_all_for_single_ground_truth_artefact() -> None:
    # Arrange
    start = datetime(2024, 1, 1, tzinfo=UTC)

    # Act
    result = MetricsCalculator().compute_all(
        tp=1,
        fp=0,
        fn=0,
        start=start,
        end=start + timedelta(seconds=1),
        dataset_name="single",
        artefacts_expected=1,
        artefacts_recovered=1,
    )

    # Assert
    assert result.precision == result.recall == result.f1_score == 1.0
    assert result.artefacts_expected == result.artefacts_recovered == 1


def test_compute_per_category_accepts_empty_and_partial_mappings() -> None:
    # Arrange
    calc = MetricsCalculator()

    # Act
    empty = calc.compute_per_category({}, {}, {})
    partial = calc.compute_per_category(
        {"event_log": 1},
        {"registry_key": 2},
        {"browser_history": 1},
    )

    # Assert
    assert empty == {}
    assert set(partial) == {"event_log", "registry_key", "browser_history"}
    assert partial["event_log"]["precision"] == 1.0
    assert partial["event_log"]["recall"] == 1.0
    assert partial["registry_key"]["precision"] == 0.0
    assert partial["browser_history"]["recall"] == 0.0
