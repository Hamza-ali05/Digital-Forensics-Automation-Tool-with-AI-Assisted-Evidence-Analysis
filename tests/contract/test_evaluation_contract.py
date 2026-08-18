"""Evaluation endpoint API contract tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from dfat.core.models.evaluation import BenchmarkResult
from tests.contract.conftest import AuthedClient


def test_run_benchmark_returns_metrics(
    admin_client: AuthedClient,
    sample_benchmark_result: BenchmarkResult,
) -> None:
    evaluation_service = AsyncMock()
    evaluation_service.run_benchmark_for_dataset = AsyncMock(
        return_value=sample_benchmark_result
    )
    container = admin_client.client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        response = admin_client.post(
            "/api/v1/evaluation/benchmark",
            json={
                "evidence_id": "ev-1",
                "ground_truth_dataset": "dfrws_sample",
                "dataset_source": "dfrws",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["benchmark_id"] == sample_benchmark_result.benchmark_id
        assert "precision" in body
        assert "recall" in body
        assert "f1_score" in body
    finally:
        container.services.evaluation_service.reset_override()


def test_get_results_returns_history(
    analyst_client: AuthedClient,
    sample_benchmark_result: BenchmarkResult,
) -> None:
    evaluation_service = AsyncMock()
    evaluation_service.get_benchmark_results = AsyncMock(
        return_value=[sample_benchmark_result]
    )
    container = analyst_client.client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        response = analyst_client.get("/api/v1/evaluation/benchmark/results")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert body[0]["benchmark_id"] == sample_benchmark_result.benchmark_id
    finally:
        container.services.evaluation_service.reset_override()


def test_submit_usability_without_auth_returns_200(
    authenticated_client: TestClient,
) -> None:
    evaluation_service = AsyncMock()
    evaluation_service.collect_usability_response = AsyncMock(
        return_value="11111111-1111-1111-1111-111111111111"
    )
    container = authenticated_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        response = authenticated_client.post(
            "/api/v1/evaluation/usability/respond",
            json={
                "ratings": {"usefulness": 5, "accuracy": 4, "clarity": 5},
                "free_text": None,
            },
        )
        # Route returns 201 Created.
        assert response.status_code == 201
        assert response.json()["participant_id"]
    finally:
        container.services.evaluation_service.reset_override()


def test_submit_usability_invalid_ratings_returns_422(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.post(
        "/api/v1/evaluation/usability/respond",
        json={"ratings": {"usefulness": "not-an-int"}},
    )
    assert response.status_code == 422


def test_get_questionnaire_without_auth_returns_instrument(
    authenticated_client: TestClient,
) -> None:
    evaluation_service = AsyncMock()
    evaluation_service.get_questionnaire_instrument = MagicMock(
        return_value={
            "instrument_version": "1.0.0",
            "questions": [{"id": "Q1", "text": "Useful?", "type": "likert"}],
        }
    )
    container = authenticated_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        response = authenticated_client.get(
            "/api/v1/evaluation/usability/questionnaire"
        )
        assert response.status_code == 200
        body = response.json()
        assert "instrument_version" in body or "questions" in body
    finally:
        container.services.evaluation_service.reset_override()


def test_usability_results_require_auth(
    authenticated_client: TestClient,
    admin_client: AuthedClient,
) -> None:
    evaluation_service = AsyncMock()
    evaluation_service.get_usability_analysis = AsyncMock(
        return_value={"total_responses": 1, "usefulness_percentage": 80.0}
    )
    container = authenticated_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        unauth = authenticated_client.get("/api/v1/evaluation/usability/results")
        assert unauth.status_code in (401, 403)

        auth = admin_client.get("/api/v1/evaluation/usability/results")
        assert auth.status_code == 200
        assert auth.json()["usefulness_percentage"] == 80.0
    finally:
        container.services.evaluation_service.reset_override()
