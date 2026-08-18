"""AI endpoint API contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dfat.ai_engine.assistance.investigator_qa import QAResponse
from dfat.ai_engine.llm.connection import LLMHealthStatus
from dfat.ai_engine.validation.hallucination_guard import HallucinationReport
from dfat.api.dependencies import get_qa_assistant
from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from tests.contract.conftest import AuthedClient


async def _seed_artefacts(app_client: TestClient, evidence_id: str) -> None:
    container = app_client.app.state.container
    repo = container.repositories.artefact_repo()
    artefact_set = ArtefactSet(
        evidence_id=evidence_id,
        artefacts=[
            Artefact(
                artefact_id="art-contract-1",
                category=ArtefactCategory.RUNNING_PROCESS,
                source_evidence_id=evidence_id,
                raw_data={"name": "cmd.exe", "pid": 100},
            )
        ],
        categories_present=[ArtefactCategory.RUNNING_PROCESS],
    )
    await repo.save(artefact_set)


def test_ai_health_returns_status_without_auth(
    authenticated_client: TestClient,
) -> None:
    healthy = LLMHealthStatus(
        is_healthy=True,
        model_loaded=True,
        model_name="llama3",
        response_time_ms=10.0,
    )
    with patch(
        "dfat.ai_engine.llm.connection.LLMConnectionManager.check_health",
        new=AsyncMock(return_value=healthy),
    ):
        response = authenticated_client.get("/api/v1/ai/health")
    assert response.status_code == 200
    body = response.json()
    assert "is_healthy" in body
    assert body["model_name"] == "llama3"


@pytest.mark.asyncio
async def test_classify_returns_classifications(
    analyst_client: AuthedClient,
    authenticated_client: TestClient,
) -> None:
    evidence_id = "ev-contract-classify"
    await _seed_artefacts(authenticated_client, evidence_id)
    response = analyst_client.post(
        "/api/v1/ai/classify",
        json={"evidence_id": evidence_id, "use_fallback": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "classifications" in body
    assert isinstance(body["classifications"], list)
    assert len(body["classifications"]) >= 1


@pytest.mark.asyncio
async def test_ask_returns_answer_with_confidence(
    analyst_client: AuthedClient,
    authenticated_client: TestClient,
) -> None:
    evidence_id = "ev-contract-ask"
    await _seed_artefacts(authenticated_client, evidence_id)

    qa = QAResponse(
        answer="cmd.exe may warrant review",
        confidence=0.82,
        referenced_artefact_ids=["art-contract-1"],
        hallucination_check=HallucinationReport(
            risk_level="low",
            clean_response="cmd.exe may warrant review",
        ),
        model_used="mock-qa",
        question="What process looks suspicious?",
        timestamp=datetime.now(UTC),
    )
    mock_assistant = MagicMock()
    mock_assistant.ask = AsyncMock(return_value=qa)
    authenticated_client.app.dependency_overrides[get_qa_assistant] = (
        lambda: mock_assistant
    )
    try:
        response = analyst_client.post(
            "/api/v1/ai/ask",
            json={
                "evidence_id": evidence_id,
                "question": "What process looks suspicious?",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["response"]["answer"]
        assert body["response"]["confidence"] == 0.82
    finally:
        authenticated_client.app.dependency_overrides.pop(get_qa_assistant, None)


def test_ai_stats_requires_admin(
    admin_client: AuthedClient,
    analyst_client: AuthedClient,
) -> None:
    denied = analyst_client.get("/api/v1/ai/stats")
    assert denied.status_code == 403
    allowed = admin_client.get("/api/v1/ai/stats")
    assert allowed.status_code == 200
    assert "total_requests" in allowed.json()


def test_cache_clear_requires_admin(
    admin_client: AuthedClient,
    viewer_client: AuthedClient,
) -> None:
    denied = viewer_client.delete("/api/v1/ai/cache")
    assert denied.status_code == 403
    allowed = admin_client.delete("/api/v1/ai/cache")
    assert allowed.status_code == 200
    assert "cleared_entries" in allowed.json()
