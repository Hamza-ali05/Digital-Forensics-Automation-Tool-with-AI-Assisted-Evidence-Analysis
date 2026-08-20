"""Integration tests for FastAPI lifespan boot wiring."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dfat.app import _lifespan, create_app
from dfat.bootstrap.models import (
    InitPhase,
    InitStatus,
    PhaseResult,
    StartupReport,
    SystemReadiness,
)


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
        phases=[_phase(InitPhase.CONFIGURATION), _phase(InitPhase.DATABASE)],
        available_capabilities=["configuration", "database"],
        version="0.1.0",
        environment="testing",
        hostname="test",
    )


def _unavailable_report() -> StartupReport:
    return StartupReport(
        system_status=SystemReadiness.UNAVAILABLE,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        total_duration_ms=50.0,
        phases=[
            PhaseResult(
                phase=InitPhase.DATABASE,
                status=InitStatus.FAILED,
                duration_ms=5.0,
                message="Database unavailable",
                details={},
                error="connection refused",
                is_critical=True,
            )
        ],
        critical_failures=["database: connection refused"],
        version="0.1.0",
        environment="testing",
        hostname="test",
    )


def test_lifespan_stores_startup_report_on_app_state() -> None:
    app = create_app()
    mock_sequencer = MagicMock()
    mock_sequencer.boot = AsyncMock(return_value=_ready_report())
    mock_task_manager = MagicMock()
    mock_task_manager.start_all = AsyncMock()
    mock_shutdown = MagicMock()
    mock_shutdown.shutdown = AsyncMock()

    with (
        patch.object(app.state.container, "boot_sequencer", return_value=mock_sequencer),
        patch.object(app.state.container, "task_manager", return_value=mock_task_manager),
        patch.object(app.state.container, "shutdown_handler", return_value=mock_shutdown),
        patch("dfat.app.StartupReportPrinter.print_report"),
        patch("dfat.app.StartupReportPrinter.save_report"),
    ):
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
            assert response.status_code == 200
            body = response.json()
            assert body["system_readiness"] == "ready"
            assert "configuration" in body["available_capabilities"]

    mock_shutdown.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_unavailable_startup_raises_system_exit() -> None:
    app = FastAPI()
    container = MagicMock()
    container.logging.setup_app_logging = MagicMock()
    mock_sequencer = MagicMock()
    mock_sequencer.boot = AsyncMock(return_value=_unavailable_report())
    container.boot_sequencer.return_value = mock_sequencer
    app.state.container = container

    with (
        patch("dfat.app.StartupReportPrinter.print_report"),
        patch("dfat.app.StartupReportPrinter.save_report"),
        pytest.raises(SystemExit, match="DFAT startup failed"),
    ):
        async with _lifespan(app):
            pass


def test_ready_endpoint_includes_service_status_map() -> None:
    app = create_app()
    report = _ready_report()
    mock_sequencer = MagicMock()
    mock_sequencer.boot = AsyncMock(return_value=report)
    mock_task_manager = MagicMock()
    mock_task_manager.start_all = AsyncMock()
    mock_shutdown = MagicMock()
    mock_shutdown.shutdown = AsyncMock()

    with (
        patch.object(app.state.container, "boot_sequencer", return_value=mock_sequencer),
        patch.object(app.state.container, "task_manager", return_value=mock_task_manager),
        patch.object(app.state.container, "shutdown_handler", return_value=mock_shutdown),
        patch("dfat.app.StartupReportPrinter.print_report"),
        patch("dfat.app.StartupReportPrinter.save_report"),
    ):
        with TestClient(app) as client:
            response = client.get("/api/v1/health/ready")
            assert response.status_code == 200
            body = response.json()
            assert body["system_readiness"] == "ready"
            assert body["services"]["configuration"] == "completed"
            assert body["services"]["database"] == "completed"
