"""Integration tests for evaluation API routes (Prompt 6.20)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from dfat.core.models.evaluation import BenchmarkResult


def _auth(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.analyst_token}"}  # type: ignore[attr-defined]


def _admin_auth(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.admin_token}"}  # type: ignore[attr-defined]


def test_benchmark_run_via_api(
    app_client: TestClient,
    sample_benchmark_result: BenchmarkResult,
) -> None:
    """Verify benchmark POST runs via the evaluation API."""
    evaluation_service = AsyncMock()
    evaluation_service.run_benchmark_for_dataset = AsyncMock(
        return_value=sample_benchmark_result
    )
    container = app_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        response = app_client.post(
            "/api/v1/evaluation/benchmark",
            headers=_admin_auth(app_client),
            json={
                "evidence_id": "ev-1",
                "ground_truth_dataset": "dfrws_sample",
                "dataset_source": "dfrws",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["benchmark_id"] == sample_benchmark_result.benchmark_id
        assert body["precision"] == sample_benchmark_result.precision
        evaluation_service.run_benchmark_for_dataset.assert_awaited_once()
    finally:
        container.services.evaluation_service.reset_override()


def test_usability_response_submission(app_client: TestClient) -> None:
    """Verify usability respond endpoint requires no authentication."""
    evaluation_service = AsyncMock()
    evaluation_service.collect_usability_response = AsyncMock(
        return_value="11111111-1111-1111-1111-111111111111"
    )
    container = app_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        response = app_client.post(
            "/api/v1/evaluation/usability/respond",
            json={"ratings": {"usefulness": 5, "accuracy": 4, "clarity": 5}},
        )
        assert response.status_code == 201
        assert response.json()["participant_id"]
        evaluation_service.collect_usability_response.assert_awaited_once()
    finally:
        container.services.evaluation_service.reset_override()


def test_usability_results_require_auth(app_client: TestClient) -> None:
    """Verify usability results endpoint rejects unauthenticated callers."""
    evaluation_service = AsyncMock()
    evaluation_service.get_usability_analysis = AsyncMock(
        return_value={"total_responses": 1, "usefulness_percentage": 70.0}
    )
    container = app_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        unauth = app_client.get("/api/v1/evaluation/usability/results")
        assert unauth.status_code in {401, 403}

        auth = app_client.get(
            "/api/v1/evaluation/usability/results",
            headers=_admin_auth(app_client),
        )
        assert auth.status_code == 200
        assert auth.json()["usefulness_percentage"] == 70.0
    finally:
        container.services.evaluation_service.reset_override()


def test_dataset_listing(app_client: TestClient) -> None:
    """Verify dataset listing returns DFRWS/CFReDS collections."""
    evaluation_service = AsyncMock()
    evaluation_service.list_datasets = MagicMock(
        return_value={"dfrws": ["dfrws_sample"], "cfreds": ["cfreds_sample"]}
    )
    container = app_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        response = app_client.get(
            "/api/v1/evaluation/benchmark/datasets",
            headers=_auth(app_client),
        )
        assert response.status_code == 200
        body = response.json()
        assert "dfrws_sample" in body["dfrws"]
        assert "cfreds_sample" in body["cfreds"]
    finally:
        container.services.evaluation_service.reset_override()
