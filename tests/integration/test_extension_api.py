"""Integration tests for dataset, knowledge, ML, and threat-intel API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.knowledge.retriever import RetrievalResult
from dfat.ml.predictor import MLPrediction
from dfat.threat_intel.feed_manager import ThreatScanResult


def _auth(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.analyst_token}"}  # type: ignore[attr-defined]


def _admin_auth(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.admin_token}"}  # type: ignore[attr-defined]


def test_list_datasets_returns_empty(app_client: TestClient) -> None:
    container = app_client.app.state.container
    registry = AsyncMock()
    registry.list_datasets = AsyncMock(return_value=[])
    container.dataset_intelligence.dataset_registry.override(registry)

    try:
        response = app_client.get("/api/v1/datasets", headers=_auth(app_client))
        assert response.status_code == 200
        assert response.json() == []
    finally:
        container.dataset_intelligence.dataset_registry.reset_override()


def test_dataset_statistics(app_client: TestClient) -> None:
    container = app_client.app.state.container
    registry = AsyncMock()
    registry.get_statistics = AsyncMock(return_value={"total": 0, "by_category": {}})
    container.dataset_intelligence.dataset_registry.override(registry)

    try:
        response = app_client.get("/api/v1/datasets/statistics", headers=_auth(app_client))
        assert response.status_code == 200
        assert response.json()["statistics"]["total"] == 0
    finally:
        container.dataset_intelligence.dataset_registry.reset_override()


def test_knowledge_stats(app_client: TestClient) -> None:
    container = app_client.app.state.container
    vector_store = AsyncMock()
    vector_store.get_collection_stats = AsyncMock(return_value={"count": 0})
    ioc_kb = AsyncMock()
    ioc_kb.get_statistics = AsyncMock(return_value={"total_iocs": 0})
    graph = MagicMock()
    graph.get_statistics = MagicMock(return_value={"nodes": 0})

    container.knowledge.vector_store.override(vector_store)
    container.knowledge.ioc_knowledge_base.override(ioc_kb)
    container.knowledge.knowledge_graph.override(graph)

    try:
        response = app_client.get("/api/v1/knowledge/stats", headers=_auth(app_client))
        assert response.status_code == 200
        body = response.json()
        assert "vector_collections" in body
        assert body["ioc_statistics"]["total_iocs"] == 0
    finally:
        container.knowledge.vector_store.reset_override()
        container.knowledge.ioc_knowledge_base.reset_override()
        container.knowledge.knowledge_graph.reset_override()


def test_knowledge_query(app_client: TestClient) -> None:
    container = app_client.app.state.container
    retriever = AsyncMock()
    retriever.retrieve = AsyncMock(
        return_value=RetrievalResult(
            query="malware",
            total_results=0,
            sources_queried=["vector"],
            retrieval_time_ms=1.0,
        )
    )
    container.knowledge.unified_retriever.override(retriever)

    try:
        response = app_client.post(
            "/api/v1/knowledge/query",
            headers=_auth(app_client),
            json={"query": "malware", "max_results": 5},
        )
        assert response.status_code == 200
        retriever.retrieve.assert_awaited_once()
    finally:
        container.knowledge.unified_retriever.reset_override()


def test_list_ml_models(app_client: TestClient) -> None:
    container = app_client.app.state.container
    registry = MagicMock()
    registry.list_models = MagicMock(return_value=[])
    container.ml.model_registry.override(registry)

    try:
        response = app_client.get("/api/v1/ml/models", headers=_auth(app_client))
        assert response.status_code == 200
        assert response.json() == []
    finally:
        container.ml.model_registry.reset_override()


def test_ml_predict(app_client: TestClient) -> None:
    container = app_client.app.state.container
    artefact = Artefact(
        artefact_id="art-001",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        source_evidence_id="ev-001",
        raw_data={"path": "/tmp/evil.exe"},
        parsed_at=datetime(2024, 1, 15, tzinfo=UTC),
    )
    artefact_repo = AsyncMock()
    artefact_repo.get_by_artefact_id = AsyncMock(return_value=artefact)
    predictor = AsyncMock()
    predictor.predict = AsyncMock(
        return_value=MLPrediction(
            model_name="MalwareClassifier",
            model_version="1.0.0",
            artefact_id="art-001",
            prediction="malicious",
            confidence=0.91,
        )
    )

    container.repositories.artefact_repo.override(artefact_repo)
    container.ml.ml_predictor.override(predictor)

    try:
        response = app_client.post(
            "/api/v1/ml/predict",
            headers=_auth(app_client),
            json={"model_name": "MalwareClassifier", "artefact_ids": ["art-001"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["model_name"] == "MalwareClassifier"
        assert len(body["predictions"]) == 1
        assert body["predictions"][0]["prediction"] == "malicious"
    finally:
        container.repositories.artefact_repo.reset_override()
        container.ml.ml_predictor.reset_override()


def test_threat_intel_summary(app_client: TestClient) -> None:
    container = app_client.app.state.container
    feed_manager = AsyncMock()
    feed_manager.get_intel_summary = AsyncMock(return_value={"yara_rules": 0, "sigma_rules": 0})
    container.threat_intel.feed_manager.override(feed_manager)

    try:
        response = app_client.get("/api/v1/threat-intel/summary", headers=_auth(app_client))
        assert response.status_code == 200
        assert "summary" in response.json()
    finally:
        container.threat_intel.feed_manager.reset_override()


def test_mitre_coverage(app_client: TestClient) -> None:
    response = app_client.get("/api/v1/threat-intel/mitre", headers=_auth(app_client))
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["techniques"], list)
    assert isinstance(body["tactics"], dict)
    assert len(body["techniques"]) > 0


def test_yara_rules_list(app_client: TestClient) -> None:
    response = app_client.get("/api/v1/threat-intel/yara/rules", headers=_auth(app_client))
    assert response.status_code == 200
    body = response.json()
    assert "rule_files" in body
    assert "loaded_count" in body


def test_sigma_rules_list(app_client: TestClient) -> None:
    response = app_client.get("/api/v1/threat-intel/sigma/rules", headers=_auth(app_client))
    assert response.status_code == 200
    body = response.json()
    assert "rules" in body
    assert "loaded_count" in body


def test_threat_intel_scan(app_client: TestClient) -> None:
    container = app_client.app.state.container
    artefact_set = ArtefactSet(
        evidence_id="ev-001",
        artefacts=[],
        parsed_at=datetime(2024, 1, 15, tzinfo=UTC),
    )
    artefact_repo = AsyncMock()
    artefact_repo.get = AsyncMock(return_value=artefact_set)
    feed_manager = AsyncMock()
    feed_manager.scan_artefacts_against_intel = AsyncMock(
        return_value=ThreatScanResult(
            total_findings=0,
            scan_duration_ms=2.5,
        )
    )

    container.repositories.artefact_repo.override(artefact_repo)
    container.threat_intel.feed_manager.override(feed_manager)

    try:
        response = app_client.post(
            "/api/v1/threat-intel/scan",
            headers=_auth(app_client),
            json={"evidence_id": "ev-001"},
        )
        assert response.status_code == 200
        assert response.json()["total_findings"] == 0
    finally:
        container.repositories.artefact_repo.reset_override()
        container.threat_intel.feed_manager.reset_override()


def test_datasets_forbidden_for_viewer(app_client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {app_client.viewer_token}"}  # type: ignore[attr-defined]
    response = app_client.get("/api/v1/datasets", headers=headers)
    assert response.status_code == 403


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/datasets/scan", "post"),
        ("/api/v1/ml/train", "post"),
        ("/api/v1/ml/retrain", "post"),
    ],
)
def test_admin_only_endpoints_reject_analyst(
    app_client: TestClient,
    path: str,
    method: str,
) -> None:
    payload = {"model_name": "MalwareClassifier"} if "train" in path else {}
    response = getattr(app_client, method)(path, headers=_auth(app_client), json=payload)
    assert response.status_code == 403
