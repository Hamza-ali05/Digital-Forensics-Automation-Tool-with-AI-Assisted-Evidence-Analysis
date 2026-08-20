"""Integration tests for system monitoring and diagnostics endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from dfat.bootstrap.models import (
    InitPhase,
    InitStatus,
    PhaseResult,
    StartupReport,
    SystemReadiness,
)
from dfat.runtime.task_manager import BackgroundTaskManager


def _phase(phase: InitPhase, status: InitStatus = InitStatus.COMPLETED) -> PhaseResult:
    return PhaseResult(
        phase=phase,
        status=status,
        duration_ms=1.0,
        message=f"{phase.value} ok",
        details={},
        is_critical=False,
    )


def _ready_report() -> StartupReport:
    return StartupReport(
        system_status=SystemReadiness.READY,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        total_duration_ms=100.0,
        phases=[
            _phase(InitPhase.CONFIGURATION),
            _phase(InitPhase.DATABASE),
            _phase(InitPhase.BACKGROUND_WORKERS),
            _phase(InitPhase.LLM_SERVICE),
            _phase(InitPhase.RAG_PIPELINE),
            _phase(InitPhase.ML_MODELS),
            _phase(InitPhase.THREAT_INTELLIGENCE),
            _phase(InitPhase.KNOWLEDGE_BASE),
            _phase(InitPhase.IOC_DATABASE),
            _phase(InitPhase.EVALUATION),
        ],
        available_capabilities=["configuration", "database", "background_workers"],
        version="0.1.0",
        environment="testing",
        hostname="test",
    )


@pytest.fixture
def booted_app_client(app_client: TestClient) -> TestClient:
    """Simulate successful bootstrap state on the shared integration client."""
    report = _ready_report()
    task_manager = BackgroundTaskManager()
    task_manager.register("HealthMonitor", AsyncMock(), interval_seconds=30)

    app_client.app.state.startup_report = report
    app_client.app.state.system_readiness = report.system_status
    app_client.app.state.task_manager = task_manager
    return app_client


def test_startup_report_accessible_without_auth(booted_app_client: TestClient) -> None:
    response = booted_app_client.get("/api/v1/system/startup")

    assert response.status_code == 200
    body = response.json()
    assert body["system_status"] == "ready"
    assert "phases" in body
    assert isinstance(body["phases"], list)
    assert "available_capabilities" in body


def test_system_status_reflects_service_health(booted_app_client: TestClient) -> None:
    response = booted_app_client.get("/api/v1/system/status")

    assert response.status_code == 200
    body = response.json()
    assert body["system_readiness"] in {
        "initializing",
        "ready",
        "degraded",
        "unavailable",
        "shutting_down",
    }
    assert "database" in body["services"]
    assert "is_healthy" in body["services"]["database"]
    assert "degraded_mode" in body


def test_system_capabilities_lists_features(booted_app_client: TestClient) -> None:
    response = booted_app_client.get("/api/v1/system/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["parsers"], dict)
    assert set(body["ai"].keys()) == {"llm", "rag", "ml"}
    assert set(body["threat_intel"].keys()) == {"yara", "sigma", "mitre"}
    assert set(body["knowledge"].keys()) == {"vector_store", "graph", "ioc_db"}
    assert set(body["benchmarks"].keys()) == {"dfrws", "cfreds"}


def test_admin_resources_and_tasks_require_admin(booted_app_client: TestClient) -> None:
    anonymous_resources = booted_app_client.get("/api/v1/system/resources")
    viewer_resources = booted_app_client.get(
        "/api/v1/system/resources",
        headers={"Authorization": f"Bearer {booted_app_client.viewer_token}"},  # type: ignore[attr-defined]
    )
    admin_resources = booted_app_client.get(
        "/api/v1/system/resources",
        headers={"Authorization": f"Bearer {booted_app_client.admin_token}"},  # type: ignore[attr-defined]
    )

    assert anonymous_resources.status_code in (401, 403)
    assert viewer_resources.status_code == 403
    assert admin_resources.status_code == 200
    resources = admin_resources.json()
    assert "memory_percent" in resources
    assert "disk_percent" in resources
    assert "timestamp" in resources

    admin_tasks = booted_app_client.get(
        "/api/v1/system/tasks",
        headers={"Authorization": f"Bearer {booted_app_client.admin_token}"},  # type: ignore[attr-defined]
    )
    assert admin_tasks.status_code == 200
    tasks = admin_tasks.json()["tasks"]
    assert "HealthMonitor" in tasks
    assert "is_running" in tasks["HealthMonitor"]


def test_diagnostics_redacts_secrets(booted_app_client: TestClient) -> None:
    response = booted_app_client.get(
        "/api/v1/system/diagnostics",
        headers={"Authorization": f"Bearer {booted_app_client.admin_token}"},  # type: ignore[attr-defined]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["config_summary"]["auth"]["secret_key"] == "[REDACTED]"
    assert body["startup_report"]["system_status"] == "ready"
    assert "capabilities" in body
    assert "services" in body
    assert "resources" in body
    assert "tasks" in body
