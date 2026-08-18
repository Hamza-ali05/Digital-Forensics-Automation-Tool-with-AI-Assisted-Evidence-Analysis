"""RBAC contract tests across roles and resources."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from jose import jwt

from dfat.ai_engine.llm.connection import LLMHealthStatus
from tests.conftest import TEST_JWT_SECRET
from tests.contract.conftest import AuthedClient, FakePipelineOrchestrator


def test_admin_can_access_all_endpoints(admin_client: AuthedClient) -> None:
    assert admin_client.get("/api/v1/users/me").status_code == 200
    assert admin_client.get("/api/v1/users").status_code == 200
    assert admin_client.get("/api/v1/cases").status_code == 200
    assert admin_client.get("/api/v1/evidence/inventory").status_code == 200
    assert admin_client.get("/api/v1/pipeline/jobs").status_code == 200
    assert admin_client.get("/api/v1/ai/stats").status_code == 200
    assert admin_client.get("/api/v1/health").status_code == 200


def test_investigator_can_create_cases(
    investigator_client: AuthedClient,
) -> None:
    response = investigator_client.post(
        "/api/v1/cases",
        json={"case_name": "Investigator Case", "description": "ok"},
    )
    assert response.status_code == 201


def test_investigator_cannot_manage_users(
    investigator_client: AuthedClient,
) -> None:
    response = investigator_client.get("/api/v1/users")
    assert response.status_code == 403


def test_analyst_can_run_analysis(
    analyst_client: AuthedClient,
    fake_orchestrator: FakePipelineOrchestrator,
) -> None:
    response = analyst_client.post(
        "/api/v1/pipeline/run",
        json={
            "evidence_id": "ev-rbac-1",
            "case_id": "case-rbac-1",
            "mode": "full",
            "use_fallback": True,
        },
    )
    assert response.status_code == 202


def test_analyst_cannot_create_cases(analyst_client: AuthedClient) -> None:
    response = analyst_client.post(
        "/api/v1/cases",
        json={"case_name": "Denied", "description": "analyst"},
    )
    assert response.status_code == 403


def test_viewer_can_only_read_reports(viewer_client: AuthedClient) -> None:
    response = viewer_client.get("/api/v1/reports/missing-report-rbac")
    assert response.status_code in (200, 404)
    assert response.status_code != 403

    eval_resp = viewer_client.get("/api/v1/evaluation/benchmark/results")
    assert eval_resp.status_code in (200, 404, 500)


def test_viewer_cannot_create_anything(viewer_client: AuthedClient) -> None:
    case = viewer_client.post(
        "/api/v1/cases",
        json={"case_name": "Nope", "description": "viewer"},
    )
    assert case.status_code == 403

    evidence = viewer_client.post(
        "/api/v1/evidence/register",
        json={
            "file_path": "/tmp/x.dd",
            "case_id": "c1",
            "evidence_type": "disk_image",
        },
    )
    assert evidence.status_code == 403

    pipeline = viewer_client.post(
        "/api/v1/pipeline/run",
        json={"evidence_id": "e1", "case_id": "c1", "mode": "full"},
    )
    assert pipeline.status_code == 403


def test_unauthenticated_gets_401_on_protected(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/api/v1/users/me")
    assert response.status_code in (401, 403)


def test_unauthenticated_can_access_health(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_unauthenticated_can_access_questionnaire(
    authenticated_client: TestClient,
) -> None:
    evaluation_service = MagicMock()
    evaluation_service.get_questionnaire_instrument = MagicMock(
        return_value={"instrument_version": "1.0.0", "questions": []}
    )
    container = authenticated_client.app.state.container
    container.services.evaluation_service.override(evaluation_service)
    try:
        response = authenticated_client.get(
            "/api/v1/evaluation/usability/questionnaire"
        )
        assert response.status_code == 200
    finally:
        container.services.evaluation_service.reset_override()


def test_unauthenticated_can_access_ai_health(
    authenticated_client: TestClient,
) -> None:
    healthy = LLMHealthStatus(
        is_healthy=False,
        model_loaded=False,
        model_name="llama3",
        response_time_ms=0.0,
    )
    with patch(
        "dfat.ai_engine.llm.connection.LLMConnectionManager.check_health",
        new=AsyncMock(return_value=healthy),
    ):
        response = authenticated_client.get("/api/v1/ai/health")
    assert response.status_code == 200


def test_expired_token_returns_401(
    authenticated_client: TestClient,
    seeded_db: dict[str, Any],
) -> None:
    now = datetime.now(UTC)
    payload = {
        "sub": seeded_db["user_ids"]["admin"],
        "username": "admin",
        "role": "admin",
        "type": "access",
        "jti": "expired-jti",
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    response = authenticated_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
