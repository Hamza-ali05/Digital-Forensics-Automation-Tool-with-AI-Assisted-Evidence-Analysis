"""Unit tests for usability response analyzer and Tobin comparison (Prompt 6.18)."""

from __future__ import annotations

import math

from dfat.core.models.evaluation import UsabilityResponse
from dfat.evaluation.usability.response_analyzer import ResponseAnalyzer
from dfat.evaluation.usability.tobin_comparison import TobinComparison


def _response(
    *,
    usefulness: int = 4,
    accuracy: int = 4,
    clarity: int = 4,
    q1: int | None = None,
    q4: int | None = None,
    comparative: int | None = None,
    free_text: str | None = None,
) -> UsabilityResponse:
    """Build a UsabilityResponse for analyzer tests."""
    return UsabilityResponse(
        participant_id="11111111-1111-1111-1111-111111111111",
        usefulness_rating=usefulness,
        accuracy_rating=accuracy,
        clarity_rating=clarity,
        q1_rating=q1,
        q4_rating=q4,
        comparative_rating=comparative,
        free_text_feedback=free_text,
    )


def test_usefulness_percentage_calculation() -> None:
    """Verify Tobin metric uses avg(Q1, Q4) >= 4, not rounded usefulness alone."""
    # avg(5, 3) = 4.0 → counts; avg(5, 2) = 3.5 → does not; usefulness=4 alone → counts
    responses = [
        _response(usefulness=4, q1=5, q4=3),  # avg 4.0 → yes
        _response(usefulness=4, q1=5, q4=2),  # avg 3.5 → no (rounded usefulness was 4)
        _response(usefulness=5, q1=5, q4=5),  # avg 5.0 → yes
    ]
    pct = ResponseAnalyzer(responses).compute_usefulness_percentage()
    assert abs(pct - (2 / 3) * 100) < 1e-9


test_usefulness_percentage_uses_q1_q4_average = test_usefulness_percentage_calculation


def test_tobin_comparison_meets_benchmark() -> None:
    """Verify Tobin comparison marks tool > 74% as meeting/exceeding benchmark."""
    assert TobinComparison.TOBIN_USEFULNESS_PERCENTAGE == 74.0
    result = TobinComparison().compare(tool_usefulness_pct=80.0, tool_sample_size=10)
    assert result.tobin_percentage == 74.0
    assert result.difference == 6.0
    assert result.meets_benchmark is True
    assert result.exceeds_benchmark is True
    assert "exceeds" in result.comparison_notes.lower()


test_tobin_benchmark_is_74 = test_tobin_comparison_meets_benchmark


def test_tobin_comparison_below_benchmark() -> None:
    """Verify 70% usefulness is correctly identified as below Tobin's 74%."""
    result = TobinComparison().compare(tool_usefulness_pct=70.0, tool_sample_size=10)
    assert result.meets_benchmark is False
    assert result.exceeds_benchmark is False
    assert result.difference == -4.0
    assert "falls below" in result.comparison_notes.lower()


test_tobin_falls_below_benchmark = test_tobin_comparison_below_benchmark


def test_descriptive_statistics_correct() -> None:
    """Verify mean/median/std_dev and DimensionStats for known values."""
    responses = [
        _response(usefulness=4, accuracy=5, clarity=3, q1=4, q4=4, comparative=5),
        _response(usefulness=2, accuracy=3, clarity=1, q1=2, q4=2, comparative=3),
    ]
    analyzer = ResponseAnalyzer(responses)
    means = analyzer.compute_mean_ratings()
    assert means["usefulness"] == 3.0
    assert means["accuracy"] == 4.0
    assert means["clarity"] == 2.0
    assert means["comparative"] == 4.0

    medians = analyzer.compute_median_ratings()
    assert medians["accuracy"] == 4.0

    std = analyzer.compute_std_dev()
    assert abs(std["accuracy"] - math.sqrt(2.0)) < 1e-9

    stats = analyzer.compute_descriptive_statistics()
    assert stats["usefulness"].sample_size == 2
    assert stats["usefulness"].min_val == 2
    assert stats["usefulness"].max_val == 4
    assert stats["comparative"].mean == 4.0


test_descriptive_statistics_and_means = test_descriptive_statistics_correct


def test_confidence_interval() -> None:
    """Verify 95% CI uses Student's t for small n (df=1 → t=12.706)."""
    # values 1 and 5 → mean=3, sample stdev=sqrt(8)=2*sqrt(2), se=2, margin=12.706*2
    responses = [
        _response(accuracy=1, usefulness=3, clarity=3),
        _response(accuracy=5, usefulness=3, clarity=3),
    ]
    stats = ResponseAnalyzer(responses).compute_descriptive_statistics()["accuracy"]
    mean = 3.0
    se = math.sqrt(8.0) / math.sqrt(2.0)  # = 2.0
    margin = 12.706 * se
    lower, upper = stats.confidence_interval_95
    assert abs(lower - (mean - margin)) < 1e-9
    assert abs(upper - (mean + margin)) < 1e-9


test_confidence_interval_95_small_sample = test_confidence_interval


def test_generate_evaluation_report_includes_tobin_and_feedback(
    sample_usability_responses: list[UsabilityResponse],
) -> None:
    """Verify evaluation report embeds Tobin comparison and free text."""
    responses = [
        _response(q1=5, q4=5, usefulness=5, free_text="Clear summaries"),
        _response(q1=3, q4=3, usefulness=3, free_text=""),
    ]
    report = ResponseAnalyzer(responses).generate_evaluation_report()
    assert report.total_responses == 2
    assert report.usefulness_percentage == 50.0
    assert report.tobin_comparison.tobin_percentage == 74.0
    assert report.tobin_comparison.meets_benchmark is False
    assert report.qualitative_feedback == ["Clear summaries"]
    assert "usefulness" in report.dimensions
    assert "comparative" in report.dimensions

    fixture_report = ResponseAnalyzer(
        sample_usability_responses
    ).generate_evaluation_report()
    assert fixture_report.total_responses == 10
    assert abs(fixture_report.usefulness_percentage - 70.0) < 1e-9
    assert fixture_report.tobin_comparison.meets_benchmark is False

