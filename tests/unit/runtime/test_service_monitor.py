"""Unit tests for ServiceMonitor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.bootstrap.models import SystemReadiness
from dfat.runtime.service_monitor import ServiceMonitor
from dfat.settings import load_settings


def _monitor(**overrides: object) -> ServiceMonitor:
    settings = load_settings(env="development")
    db_engine = AsyncMock()
    db_engine.check_connection = AsyncMock(return_value=True)
    llm = AsyncMock()
    llm.check_health = AsyncMock(
        return_value=MagicMock(is_healthy=True, model_name="llama3", response_time_ms=10.0)
    )
    vector_store = AsyncMock()
    vector_store.list_collections = AsyncMock(return_value=["knowledge"])
    audit_logger = MagicMock(_audit_log_path=Path("data/outputs/audit.log"))
    defaults = {
        "db_engine": db_engine,
        "llm_connection": llm,
        "vector_store": vector_store,
        "settings": settings,
        "audit_logger": audit_logger,
    }
    defaults.update(overrides)
    return ServiceMonitor(**defaults)


@pytest.mark.asyncio
async def test_service_monitor_detects_database_connectivity(tmp_path: Path) -> None:
    db_engine = AsyncMock()
    db_engine.check_connection = AsyncMock(return_value=True)
    settings = load_settings(env="development")
    settings.evidence.evidence_dir = tmp_path / "evidence"
    settings.logging.audit_log_path = tmp_path / "audit.log"
    monitor = _monitor(db_engine=db_engine, settings=settings)

    result = await monitor.check_service("database")

    assert result.is_healthy is True
    assert result.details["connectivity"] is True


@pytest.mark.asyncio
async def test_service_monitor_overall_status_degraded_when_ollama_unhealthy(
    tmp_path: Path,
) -> None:
    llm = AsyncMock()
    llm.check_health = AsyncMock(return_value=MagicMock(is_healthy=False, error="down"))
    settings = load_settings(env="development")
    settings.evidence.evidence_dir = tmp_path / "evidence"
    settings.logging.audit_log_path = tmp_path / "audit.log"
    monitor = _monitor(llm_connection=llm, settings=settings)

    await monitor.check_all()

    assert monitor.get_overall_status() == SystemReadiness.DEGRADED


@pytest.mark.asyncio
async def test_service_monitor_unavailable_when_database_unhealthy(tmp_path: Path) -> None:
    db_engine = AsyncMock()
    db_engine.check_connection = AsyncMock(return_value=False)
    settings = load_settings(env="development")
    settings.evidence.evidence_dir = tmp_path / "evidence"
    settings.logging.audit_log_path = tmp_path / "audit.log"
    monitor = _monitor(db_engine=db_engine, settings=settings)

    await monitor.check_all()

    assert monitor.get_overall_status() == SystemReadiness.UNAVAILABLE


@pytest.mark.asyncio
async def test_service_monitor_health_history_filters_by_minutes(tmp_path: Path) -> None:
    settings = load_settings(env="development")
    settings.evidence.evidence_dir = tmp_path / "evidence"
    settings.logging.audit_log_path = tmp_path / "audit.log"
    monitor = _monitor(settings=settings)

    fresh = await monitor.check_service("database")
    stale = fresh.model_copy(deep=True)
    stale.last_checked = datetime.now(UTC) - timedelta(minutes=120)
    monitor._history["database"].appendleft(stale)

    history = monitor.get_health_history("database", minutes=60)

    assert len(history) == 1
    assert history[0].last_checked >= datetime.now(UTC) - timedelta(minutes=60)
