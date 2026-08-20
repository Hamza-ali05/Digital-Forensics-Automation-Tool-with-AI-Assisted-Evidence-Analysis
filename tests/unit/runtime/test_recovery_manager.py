"""Unit tests for RecoveryManager automatic service recovery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from datetime import UTC, datetime

import pytest

from dfat.bootstrap.models import ServiceHealth, SystemReadiness
from dfat.core.enums import PipelineStage
from dfat.runtime.recovery_manager import RecoveryManager


def _healthy(name: str) -> ServiceHealth:
    return ServiceHealth(
        service_name=name,
        is_healthy=True,
        last_checked=datetime.now(UTC),
        response_time_ms=1.0,
        details={},
    )


def _unhealthy(name: str) -> ServiceHealth:
    return ServiceHealth(
        service_name=name,
        is_healthy=False,
        last_checked=datetime.now(UTC),
        response_time_ms=1.0,
        details={"error": "down"},
    )


def _manager(**overrides: object) -> RecoveryManager:
    service_monitor = MagicMock()
    service_monitor.check_service = AsyncMock(return_value=_healthy("database"))
    service_monitor._db_engine = AsyncMock()
    service_monitor._vector_store = AsyncMock()
    service_monitor._vector_store.list_collections = AsyncMock(return_value=["knowledge"])

    boot_sequencer = MagicMock()
    boot_sequencer._knowledge_initializer = MagicMock()
    boot_sequencer._knowledge_initializer.initialize_knowledge_base = AsyncMock()

    audit_service = AsyncMock()

    defaults = {
        "service_monitor": service_monitor,
        "boot_sequencer": boot_sequencer,
        "audit_service": audit_service,
    }
    defaults.update(overrides)
    return RecoveryManager(**defaults)


@pytest.mark.asyncio
async def test_database_recovery_retries_with_backoff() -> None:
    db_engine = AsyncMock()
    db_engine.check_connection = AsyncMock(side_effect=[False, False, True])
    service_monitor = MagicMock()
    service_monitor._db_engine = db_engine
    service_monitor.check_service = AsyncMock(return_value=_healthy("database"))
    manager = _manager(service_monitor=service_monitor)

    recovered = await manager.attempt_recovery("database")

    assert recovered is True
    assert db_engine.check_connection.await_count == 3


@pytest.mark.asyncio
async def test_ollama_failure_activates_rule_based_fallback() -> None:
    service_monitor = MagicMock()
    service_monitor.check_service = AsyncMock(return_value=_healthy("ollama"))
    manager = _manager(service_monitor=service_monitor)

    recovered = await manager.attempt_recovery("ollama")

    assert recovered is True
    assert manager.is_fallback_active("ollama") is True


@pytest.mark.asyncio
async def test_recovery_attempts_logged_to_audit_trail() -> None:
    audit_service = AsyncMock()
    service_monitor = MagicMock()
    service_monitor.check_service = AsyncMock(return_value=_healthy("ollama"))
    manager = _manager(service_monitor=service_monitor, audit_service=audit_service)

    await manager.attempt_recovery("ollama")

    actions = [call.kwargs["action"] for call in audit_service.log_action.await_args_list]
    assert "SERVICE_RECOVERY_ATTEMPT" in actions
    assert "LLM_FALLBACK_ACTIVATED" in actions
    assert "SERVICE_RECOVERY_COMPLETED" in actions
    assert all(
        call.kwargs["stage"] == PipelineStage.ACQUISITION
        for call in audit_service.log_action.await_args_list
    )


@pytest.mark.asyncio
async def test_on_service_failure_triggers_recovery_after_threshold() -> None:
    manager = _manager()
    manager.attempt_recovery = AsyncMock(return_value=True)

    await manager.on_service_failure("database", consecutive_failures=4)

    manager.attempt_recovery.assert_awaited_once_with("database")


@pytest.mark.asyncio
async def test_on_service_failure_critical_enters_degraded_mode() -> None:
    audit_service = AsyncMock()
    manager = _manager(audit_service=audit_service)
    manager.attempt_recovery = AsyncMock()

    await manager.on_service_failure("database", consecutive_failures=11)

    assert manager.degraded_mode is True
    manager.attempt_recovery.assert_not_awaited()
    critical_calls = [
        call
        for call in audit_service.log_action.await_args_list
        if call.kwargs["action"] == "SERVICE_FAILURE_CRITICAL"
    ]
    assert len(critical_calls) == 1
    assert critical_calls[0].kwargs["details"]["system_readiness"] == SystemReadiness.DEGRADED.value
