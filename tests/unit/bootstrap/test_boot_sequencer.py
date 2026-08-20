"""Unit tests for BootSequencer and StartupReportPrinter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.bootstrap.boot_sequencer import BootSequencer
from dfat.bootstrap.models import (
    InitPhase,
    InitStatus,
    PhaseResult,
    StartupReport,
    SystemReadiness,
)
from dfat.bootstrap.startup_report import StartupReportPrinter
from dfat.settings import load_settings


def _ok(phase: InitPhase, *, critical: bool = False, ms: float = 10.0) -> PhaseResult:
    return PhaseResult(
        phase=phase,
        status=InitStatus.COMPLETED,
        duration_ms=ms,
        message=f"{phase.value} ok",
        details={},
        is_critical=critical,
    )


def _failed(phase: InitPhase, *, critical: bool, message: str = "boom") -> PhaseResult:
    return PhaseResult(
        phase=phase,
        status=InitStatus.FAILED,
        duration_ms=5.0,
        message=message,
        details={},
        error=message,
        is_critical=critical,
    )


def _degraded(phase: InitPhase, caps: list[str] | None = None) -> PhaseResult:
    return PhaseResult(
        phase=phase,
        status=InitStatus.DEGRADED,
        duration_ms=8.0,
        message=f"{phase.value} degraded",
        details={},
        is_critical=False,
        degraded_capabilities=caps or [phase.value],
    )


def _mock_initializer(result: PhaseResult) -> Any:
    def _copy(*_args: Any, **_kwargs: Any) -> PhaseResult:
        return result.model_copy(deep=True)

    init = MagicMock()
    init.initialize = AsyncMock(side_effect=_copy)
    init.initialize_knowledge_base = AsyncMock(side_effect=_copy)
    init.initialize_ioc = AsyncMock(side_effect=_copy)
    init.initialize_ml = AsyncMock(side_effect=_copy)
    init.initialize_llm = AsyncMock(side_effect=_copy)
    init.initialize_rag = AsyncMock(side_effect=_copy)
    init.validate = AsyncMock(side_effect=_copy)
    init.validate_and_create = AsyncMock(side_effect=_copy)
    return init


def _sequencer_with_mocks(
    *,
    overrides: dict[str, Any] | None = None,
) -> BootSequencer:
    settings = load_settings(env="development")
    defaults: dict[str, Any] = {
        "config_validator": _mock_initializer(_ok(InitPhase.CONFIGURATION, critical=True)),
        "directory_manager": _mock_initializer(_ok(InitPhase.DIRECTORIES, critical=True)),
        "db_initializer": _mock_initializer(_ok(InitPhase.DATABASE, critical=True)),
        "auth_initializer": _mock_initializer(_ok(InitPhase.AUTHENTICATION, critical=True)),
        "audit_initializer": _mock_initializer(_ok(InitPhase.AUDIT_LOGGING, critical=True)),
        "parser_initializer": _mock_initializer(_ok(InitPhase.FORENSIC_PARSERS)),
        "dataset_initializer": _mock_initializer(_ok(InitPhase.DATASET_DISCOVERY)),
        "knowledge_initializer": _mock_initializer(_ok(InitPhase.KNOWLEDGE_BASE)),
        "ai_initializer": _mock_initializer(_ok(InitPhase.LLM_SERVICE)),
        "threat_intel_initializer": _mock_initializer(_ok(InitPhase.THREAT_INTELLIGENCE)),
        "reporting_initializer": _mock_initializer(_ok(InitPhase.REPORTING, critical=True)),
        "evaluation_initializer": _mock_initializer(_ok(InitPhase.EVALUATION)),
        "worker_initializer": _mock_initializer(_ok(InitPhase.BACKGROUND_WORKERS)),
    }
    if overrides:
        defaults.update(overrides)
    return BootSequencer(settings=settings, **defaults)


@pytest.mark.asyncio
async def test_boot_sequence_runs_all_phases_in_order() -> None:
    sequencer = _sequencer_with_mocks()
    report = await sequencer.boot()

    assert report.system_status == SystemReadiness.READY
    assert len(report.phases) == 16
    expected_order = [phase for phase, _, _ in sequencer.BOOT_SEQUENCE]
    assert [p.phase for p in report.phases] == expected_order
    assert report.critical_failures == []
    assert report.completed_at is not None
    assert report.total_duration_ms >= 0
    assert report.version


@pytest.mark.asyncio
async def test_critical_failure_aborts_with_unavailable() -> None:
    failing_db = _mock_initializer(
        _failed(InitPhase.DATABASE, critical=True, message="connection refused")
    )
    sequencer = _sequencer_with_mocks(overrides={"db_initializer": failing_db})

    report = await sequencer.boot()

    assert report.system_status == SystemReadiness.UNAVAILABLE
    assert any("database" in f for f in report.critical_failures)
    assert "connection refused" in report.critical_failures[0]
    # Aborted after DATABASE — later phases must not run.
    phase_names = [p.phase for p in report.phases]
    assert InitPhase.DATABASE in phase_names
    assert InitPhase.AUTHENTICATION not in phase_names
    assert InitPhase.BACKGROUND_WORKERS not in phase_names


@pytest.mark.asyncio
async def test_non_critical_failure_degrades() -> None:
    degraded_ai = _mock_initializer(_degraded(InitPhase.LLM_SERVICE, ["llm_service"]))
    sequencer = _sequencer_with_mocks(overrides={"ai_initializer": degraded_ai})

    report = await sequencer.boot()

    assert report.system_status == SystemReadiness.DEGRADED
    assert report.critical_failures == []
    assert len(report.phases) == 16
    assert "llm_service" in report.degraded_services or InitPhase.LLM_SERVICE.value in (
        report.degraded_services
    )


@pytest.mark.asyncio
async def test_unexpected_exception_becomes_failed_phase() -> None:
    boom = MagicMock()
    boom.initialize = AsyncMock(side_effect=RuntimeError("unexpected crash"))
    sequencer = _sequencer_with_mocks(overrides={"parser_initializer": boom})

    report = await sequencer.boot()

    assert report.system_status == SystemReadiness.DEGRADED
    parser_result = next(p for p in report.phases if p.phase == InitPhase.FORENSIC_PARSERS)
    assert parser_result.status == InitStatus.FAILED
    assert "unexpected crash" in (parser_result.error or "")


@pytest.mark.asyncio
async def test_startup_banner_prints_correctly(capsys: pytest.CaptureFixture[str]) -> None:
    report = StartupReport(
        system_status=SystemReadiness.READY,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        total_duration_ms=3200.0,
        phases=[
            _ok(InitPhase.CONFIGURATION, critical=True, ms=12),
            _ok(InitPhase.DATABASE, critical=True, ms=234),
            _degraded(InitPhase.LLM_SERVICE, ["llm_service"]),
        ],
        version="0.1.0",
        environment="development",
        hostname="test-host",
    )
    StartupReportPrinter().print_report(report)
    out = capsys.readouterr().out

    assert "DFAT — Digital Forensics Automation Tool" in out
    assert "Version: 0.1.0" in out
    assert "Environment: development" in out
    assert "System Status: READY" in out
    assert "Startup Time: 3.2 seconds" in out
    assert "API: http://localhost:8000/api/v1" in out
    assert "Docs: http://localhost:8000/docs" in out
    assert "Frontend: http://localhost:3000" in out
    assert "╔" in out and "╚" in out


def test_save_report_writes_json(tmp_path: Path) -> None:
    report = StartupReport(
        system_status=SystemReadiness.DEGRADED,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        total_duration_ms=100.0,
        phases=[_degraded(InitPhase.EVALUATION)],
        degraded_services=["evaluation"],
        version="0.1.0",
        environment="testing",
        hostname="host",
    )
    path = tmp_path / "startup" / "report.json"
    StartupReportPrinter().save_report(report, path)

    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["system_status"] == "degraded"
    assert payload["version"] == "0.1.0"
    assert len(payload["phases"]) == 1
