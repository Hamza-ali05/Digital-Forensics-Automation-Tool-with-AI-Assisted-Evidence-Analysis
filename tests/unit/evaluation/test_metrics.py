"""Unit tests for evaluation metrics calculator."""

from __future__ import annotations

from datetime import UTC, datetime

from dfat.evaluation.benchmark.metrics import MetricsCalculator


def test_compute_precision_with_known_tp_fp() -> None:
    """Verify precision = TP / (TP + FP) for known counts."""
    # Arrange
    calc = MetricsCalculator()

    # Act
    precision = calc.compute_precision(true_positives=8, false_positives=2)

    # Assert
    assert precision == 0.8


def test_compute_recall_with_known_tp_fn() -> None:
    """Verify recall = TP / (TP + FN) for known counts."""
    # Arrange
    calc = MetricsCalculator()

    # Act
    recall = calc.compute_recall(true_positives=8, false_negatives=2)

    # Assert
    assert recall == 0.8


def test_compute_f1_with_known_precision_recall() -> None:
    """Verify F1 for equal precision and recall."""
    # Arrange
    calc = MetricsCalculator()

    # Act
    f1 = calc.compute_f1(precision=0.8, recall=0.8)

    # Assert
    assert abs(f1 - 0.8) < 1e-9


def test_compute_precision_returns_zero_when_denominator_zero() -> None:
    """Verify precision is 0.0 when TP + FP is zero."""
    # Arrange / Act / Assert
    assert MetricsCalculator().compute_precision(0, 0) == 0.0


def test_compute_time_to_triage_non_negative() -> None:
    """Verify time-to-triage is non-negative for ordered timestamps."""
    # Arrange
    calc = MetricsCalculator()
    start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    end = datetime(2024, 1, 1, 12, 0, 5, tzinfo=UTC)

    # Act
    elapsed = calc.compute_time_to_triage(start, end)

    # Assert
    assert elapsed == 5.0
