"""Unit tests for evaluation metrics calculator (Prompt 6.13)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dfat.core.exceptions import MetricsCalculationError
from dfat.evaluation.benchmark.metrics import MetricsCalculator


def test_compute_precision_with_known_tp_fp() -> None:
    """Verify precision = TP / (TP + FP) for known counts."""
    assert MetricsCalculator().compute_precision(tp=8, fp=2) == 0.8


def test_compute_recall_with_known_tp_fn() -> None:
    """Verify recall = TP / (TP + FN) for known counts."""
    assert MetricsCalculator().compute_recall(tp=8, fn=2) == 0.8


def test_compute_f1_with_known_precision_recall() -> None:
    """Verify F1 for equal precision and recall."""
    f1 = MetricsCalculator().compute_f1(precision=0.8, recall=0.8)
    assert abs(f1 - 0.8) < 1e-9


def test_division_by_zero_returns_zero() -> None:
    """Verify precision/recall/F1/accuracy return 0.0 on empty denominators."""
    calc = MetricsCalculator()
    assert calc.compute_precision(0, 0) == 0.0
    assert calc.compute_recall(0, 0) == 0.0
    assert calc.compute_f1(0.0, 0.0) == 0.0
    assert calc.compute_accuracy(0, 0, 0) == 0.0


def test_compute_accuracy() -> None:
    """Verify accuracy = TP / (TP + FP + FN)."""
    assert MetricsCalculator().compute_accuracy(tp=5, fp=3, fn=2) == 0.5


def test_compute_time_to_triage_seconds() -> None:
    """Verify time-to-triage returns positive elapsed seconds."""
    calc = MetricsCalculator()
    start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    end = datetime(2024, 1, 1, 12, 0, 5, tzinfo=UTC)
    assert calc.compute_time_to_triage(start, end) == 5.0


def test_compute_time_to_triage_rejects_negative_duration() -> None:
    """Verify time_to_triage raises when end is not after start."""
    calc = MetricsCalculator()
    start = datetime(2024, 1, 1, 12, 0, 5, tzinfo=UTC)
    end = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    with pytest.raises(MetricsCalculationError):
        calc.compute_time_to_triage(start, end)
    with pytest.raises(MetricsCalculationError):
        calc.compute_time_to_triage(start, start)


def test_compute_all_returns_benchmark_result() -> None:
    """Verify compute_all populates BenchmarkResult fields."""
    calc = MetricsCalculator()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(seconds=12)
    result = calc.compute_all(
        tp=8,
        fp=2,
        fn=2,
        start=start,
        end=end,
        dataset_name="unit_gt",
        artefacts_expected=10,
        artefacts_recovered=10,
    )
    assert result.dataset_name == "unit_gt"
    assert result.precision == 0.8
    assert result.recall == 0.8
    assert abs(result.f1_score - 0.8) < 1e-9
    assert result.time_to_triage_seconds == 12.0
    assert result.artefacts_expected == 10
    assert result.artefacts_recovered == 10
    assert result.false_positives == 2
    assert result.false_negatives == 2
    assert result.evaluated_at is not None


def test_compute_per_category_independently() -> None:
    """Verify per-category metrics are computed independently."""
    calc = MetricsCalculator()
    per_cat = calc.compute_per_category(
        tp_by_cat={"injected_code": 4, "registry_key": 0},
        fp_by_cat={"injected_code": 1, "registry_key": 2},
        fn_by_cat={"injected_code": 1, "registry_key": 0},
    )
    assert set(per_cat) == {"injected_code", "registry_key"}
    assert abs(per_cat["injected_code"]["precision"] - (4 / 5)) < 1e-9
    assert abs(per_cat["injected_code"]["recall"] - (4 / 5)) < 1e-9
    assert per_cat["registry_key"]["precision"] == 0.0
    assert per_cat["registry_key"]["recall"] == 0.0
    assert per_cat["registry_key"]["f1"] == 0.0


# Prompt 6.20 named coverage aliases
test_precision_correct = test_compute_precision_with_known_tp_fp
test_recall_correct = test_compute_recall_with_known_tp_fn
test_f1_correct = test_compute_f1_with_known_precision_recall
test_time_to_triage_correct = test_compute_time_to_triage_seconds
test_per_category_metrics = test_compute_per_category_independently

