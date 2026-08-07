"""Integration tests for AI Analysis API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from dfat.ai_engine.llm.connection import LLMHealthStatus
from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.database.models.ai_orm import AIAnalysisRecordORM


def _analyst_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.analyst_token}"}  # type: ignore[attr-defined]


def _admin_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.admin_token}"}  # type: ignore[attr-defined]


def _viewer_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.viewer_token}"}  # type: ignore[attr-defined]


async def _seed_artefacts(app_client: TestClient, evidence_id: str) -> ArtefactSet:
    """Persist a small artefact set for AI route tests."""
    container = app_client.app.state.container
    repo = container.repositories.artefact_repo()
    artefacts = [
        Artefact(
            artefact_id="art-ai-001",
            category=ArtefactCategory.RUNNING_PROCESS,
            source_evidence_id=evidence_id,
            raw_data={"name": "mimikatz.exe", "pid": 1337},
        ),
        Artefact(
            artefact_id="art-ai-002",
            category=ArtefactCategory.NETWORK_CONNECTION,
            source_evidence_id=evidence_id,
            raw_data={"remote_ip": "1.2.3.4", "port": 443},
        ),
    ]
    artefact_set = ArtefactSet(
        evidence_id=evidence_id,
        artefacts=artefacts,
        categories_present=[
            ArtefactCategory.RUNNING_PROCESS,
            ArtefactCategory.NETWORK_CONNECTION,
        ],
    )
    await repo.save(artefact_set)
    return artefact_set


def test_ai_health_works_without_auth(app_client: TestClient) -> None:
    """Verify GET /ai/health does not require authentication."""
    healthy = LLMHealthStatus(
        is_healthy=True,
        model_loaded=True,
        model_name="llama3",
        response_time_ms=12.5,
    )
    with patch(
        "dfat.ai_engine.llm.connection.LLMConnectionManager.check_health",
        new=AsyncMock(return_value=healthy),
    ):
        response = app_client.get("/api/v1/ai/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_healthy"] is True
    assert payload["model_name"] == "llama3"


def test_ai_cache_clear_requires_admin(app_client: TestClient) -> None:
    """Verify DELETE /ai/cache rejects non-admin callers."""
    denied = app_client.delete("/api/v1/ai/cache", headers=_analyst_headers(app_client))
    assert denied.status_code == 403

    allowed = app_client.delete("/api/v1/ai/cache", headers=_admin_headers(app_client))
    assert allowed.status_code == 200
    assert "cleared_entries" in allowed.json()


def test_ai_stats_requires_admin(app_client: TestClient) -> None:
    """Verify GET /ai/stats is admin-only."""
    denied = app_client.get("/api/v1/ai/stats", headers=_viewer_headers(app_client))
    assert denied.status_code == 403

    ok = app_client.get("/api/v1/ai/stats", headers=_admin_headers(app_client))
    assert ok.status_code == 200
    assert "total_requests" in ok.json()


@pytest.mark.asyncio
async def test_classify_with_fallback_persists_record(
    app_client: TestClient,
) -> None:
    """Verify classify with use_fallback persists an AI analysis record."""
    evidence_id = "ev-ai-classify-001"
    await _seed_artefacts(app_client, evidence_id)

    response = app_client.post(
        "/api/v1/ai/classify",
        headers=_analyst_headers(app_client),
        json={"evidence_id": evidence_id, "use_fallback": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["model_used"] == "RuleBasedFallback"
    assert len(payload["classifications"]) == 2
    assert payload["analysis_record_id"]

    engine = app_client.app.state.container.database.database_engine()
    async with engine.session_factory() as session:
        result = await session.execute(
            select(AIAnalysisRecordORM).where(
                AIAnalysisRecordORM.evidence_id == evidence_id,
                AIAnalysisRecordORM.analysis_type == "classification",
            )
        )
        rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].model_used == "RuleBasedFallback"
    assert rows[0].input_artefact_count == 2


@pytest.mark.asyncio
async def test_summarize_with_fallback(app_client: TestClient) -> None:
    """Verify summarize with fallback returns a non-empty summary."""
    evidence_id = "ev-ai-summary-001"
    await _seed_artefacts(app_client, evidence_id)

    response = app_client.post(
        "/api/v1/ai/summarize",
        headers=_analyst_headers(app_client),
        json={"evidence_id": evidence_id, "use_fallback": True},
    )
    assert response.status_code == 200, response.text
    summary = response.json()["summary"]
    assert summary["full_text"]
    assert summary["model_used"] == "RuleBasedFallback"


@pytest.mark.asyncio
async def test_classify_requires_auth(app_client: TestClient) -> None:
    """Verify classify rejects unauthenticated requests."""
    response = app_client.post(
        "/api/v1/ai/classify",
        json={"evidence_id": "missing", "use_fallback": True},
    )
    assert response.status_code in (401, 403)

