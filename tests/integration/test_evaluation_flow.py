"""Evaluation flow integration tests (Prompt 9.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.evaluation.benchmark.cfreds_handler import CFReDSHandler
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.dfrws_handler import DFRWSHandler
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.evaluation.benchmark.performance import PerformanceAnalyzer
from dfat.evaluation.usability.response_analyzer import ResponseAnalyzer


def _admin(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.admin_token}"}  # type: ignore[attr-defined]


def _analyst(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.analyst_token}"}  # type: ignore[attr-defined]


def _comparator(tmp_path: Path) -> BenchmarkComparator:
    loader = GroundTruthLoader(
        tmp_path, DFRWSHandler(tmp_path), CFReDSHandler(tmp_path)
    )
    return BenchmarkComparator(
        metrics=MetricsCalculator(),
        ground_truth_loader=loader,
        audit_service=AsyncMock(),
        benchmark_repo=AsyncMock(),
        thresholds={"precision_min": 0.0, "recall_min": 0.0, "f1_min": 0.0},
    )


@pytest.mark.asyncio
async def test_benchmark_evaluation(
    tmp_path: Path,
    sample_ground_truth,
) -> None:
    """Pipeline artefacts vs ground truth → precision/recall/F1 computed correctly."""
    # Recover every ground-truth artefact using the same expected_data fields the
    # comparator normalises, plus one intentional false positive.
    recovered_artefacts = [
        Artefact(
            category=item.category,
            source_evidence_id="ev-bench",
            raw_data=dict(item.expected_data or {}),
        )
        for item in sample_ground_truth.artefacts
    ]
    recovered_artefacts.append(
        Artefact(
            category=ArtefactCategory.BROWSER_HISTORY,
            source_evidence_id="ev-bench",
            raw_data={"url": "http://false-positive.example/noise"},
        )
    )
    recovered = ArtefactSet(
        evidence_id="ev-bench",
        artefacts=recovered_artefacts,
        categories_present=list({a.category for a in recovered_artefacts}),
    )

    start = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
    end = datetime(2024, 1, 15, 12, 0, 30, tzinfo=UTC)
    result = await _comparator(tmp_path).compare(
        recovered=recovered,
        ground_truth=sample_ground_truth,
        pipeline_start=start,
        pipeline_end=end,
        dataset_name=sample_ground_truth.dataset_name,
        persist=False,
        audit=False,
    )

    expected = len(sample_ground_truth.artefacts)
    assert result.artefacts_expected == expected
    assert result.false_positives == 1
    assert result.false_negatives == 0
    assert result.precision == pytest.approx(expected / (expected + 1))
    assert result.recall == pytest.approx(1.0)
    assert result.f1_score == pytest.approx(
        2 * result.precision * result.recall / (result.precision + result.recall)
    )
    assert result.time_to_triage_seconds == pytest.approx(30.0)


def test_usability_collection(
    app_client: TestClient,
    sample_usability_responses: list[UsabilityResponse],
) -> None:
    """Submit 10 responses → analysis usefulness % and Tobin comparison."""
    # Local analyzer verifies fixture math (70% usefulness, below Tobin 74%).
    report = ResponseAnalyzer(sample_usability_responses).generate_evaluation_report()
    assert report.total_responses == 10
    assert abs(report.usefulness_percentage - 70.0) < 1e-9
    assert report.tobin_comparison.tobin_percentage == 74.0
    assert report.tobin_comparison.meets_benchmark is False
    assert report.tobin_comparison.difference == pytest.approx(-4.0)

    evaluation_service = AsyncMock()
    evaluation_service.collect_usability_response = AsyncMock(
        side_effect=[response.participant_id for response in sample_usability_responses]
    )
    evaluation_service.get_usability_analysis = AsyncMock(
        return_value={
            "total_responses": 10,
            "usefulness_percentage": 70.0,
            "tobin_comparison": report.tobin_comparison.model_dump(mode="json"),
        }
    )
    container = app_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        for response in sample_usability_responses:
            submitted = app_client.post(
                "/api/v1/evaluation/usability/respond",
                json={
                    "ratings": {
                        "usefulness": response.usefulness_rating,
                        "accuracy": response.accuracy_rating,
                        "clarity": response.clarity_rating,
                    }
                },
            )
            assert submitted.status_code == 201, submitted.text

        analysis = app_client.get(
            "/api/v1/evaluation/usability/results",
            headers=_admin(app_client),
        )
        assert analysis.status_code == 200
        body = analysis.json()
        assert body["total_responses"] == 10
        assert body["usefulness_percentage"] == 70.0
        assert body["tobin_comparison"]["tobin_percentage"] == 74.0
        assert body["tobin_comparison"]["meets_benchmark"] is False
    finally:
        container.services.evaluation_service.reset_override()


def test_performance_analytics(
    app_client: TestClient,
    sample_benchmark_result: BenchmarkResult,
) -> None:
    """Three pipeline/benchmark runs → mean/median/std_dev TTT via performance API."""
    runs = [
        sample_benchmark_result.model_copy(
            update={
                "benchmark_id": f"bench-{index}",
                "time_to_triage_seconds": ttt,
            }
        )
        for index, ttt in enumerate((10.0, 20.0, 30.0))
    ]
    analyzer = PerformanceAnalyzer(AsyncMock())
    local = analyzer.generate_performance_report(runs, baseline_ttt=60.0)
    assert local.run_count == 3
    assert local.time_stats.mean == 20.0
    assert local.time_stats.median == 20.0
    assert local.time_stats.std_dev == pytest.approx(10.0)

    evaluation_service = AsyncMock()
    evaluation_service.get_performance_report = AsyncMock(return_value=local)
    container = app_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        response = app_client.get(
            "/api/v1/evaluation/benchmark/performance",
            headers=_analyst(app_client),
            params={"dataset_name": sample_benchmark_result.dataset_name, "baseline_ttt": 60.0},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["run_count"] == 3
        assert body["time_stats"]["mean"] == 20.0
        assert body["time_stats"]["median"] == 20.0
        assert abs(body["time_stats"]["std_dev"] - 10.0) < 1e-9
        evaluation_service.get_performance_report.assert_awaited_once()
    finally:
        container.services.evaluation_service.reset_override()
