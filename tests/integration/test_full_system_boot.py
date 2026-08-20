"""Integration tests for the full DFAT bootstrap sequence (Prompt 12.14)."""

from __future__ import annotations

import pytest

from dfat.bootstrap.models import InitPhase, InitStatus, SystemReadiness
from dfat.settings import DatabaseSettings
from tests.integration.boot_helpers import (
    assert_critical_phases_completed,
    assert_system_ready_or_degraded,
    boot_container,
    dispose_container,
    phase_result,
)


@pytest.mark.asyncio
async def test_boot_sequence_completes_in_development(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Development boot completes all critical phases; system is READY or DEGRADED."""
    ctx = await boot_container(tmp_path, monkeypatch, env="development", llm_healthy=False)
    try:
        assert len(ctx.report.phases) == 16
        assert_critical_phases_completed(ctx.report)
        assert_system_ready_or_degraded(ctx.report)
    finally:
        await dispose_container(ctx.container)


@pytest.mark.asyncio
async def test_boot_sequence_aborts_on_db_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid database URL aborts startup with UNAVAILABLE and a clear error."""
    bad_url = "postgresql+asyncpg://invalid:invalid@127.0.0.1:1/dfat_missing"
    ctx = await boot_container(
        tmp_path,
        monkeypatch,
        seed_users=False,
        settings_overrides={
            "database": DatabaseSettings(
                url=bad_url,
                create_tables_on_startup=False,
                echo=False,
                pool_size=1,
                max_overflow=0,
            )
        },
    )
    try:
        assert ctx.report.system_status is SystemReadiness.UNAVAILABLE
        assert ctx.report.critical_failures
        failure_text = " ".join(ctx.report.critical_failures).lower()
        assert "database" in failure_text
        assert any(
            token in failure_text
            for token in ("connection", "failed", "database", "refused", "connect")
        )
        db_phase = phase_result(ctx.report, InitPhase.DATABASE)
        assert db_phase.status is InitStatus.FAILED
        assert db_phase.error or db_phase.message
        phase_names = {item.phase for item in ctx.report.phases}
        assert InitPhase.AUTHENTICATION not in phase_names
    finally:
        await dispose_container(ctx.container)


@pytest.mark.asyncio
async def test_boot_with_no_ollama(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without Ollama the LLM phase is DEGRADED and rule-based fallback remains active."""
    ctx = await boot_container(tmp_path, monkeypatch, llm_healthy=False)
    try:
        llm_phase = phase_result(ctx.report, InitPhase.LLM_SERVICE)
        assert llm_phase.status is InitStatus.DEGRADED
        assert "llm_service" in llm_phase.degraded_capabilities
        assert ctx.report.system_status is SystemReadiness.DEGRADED

        ai_init = ctx.container.bootstrap.ai_initializer()
        combined = await ai_init.initialize()
        assert combined.details["capabilities"]["fallback"] is True

        recovery = ctx.container.recovery_manager()
        await recovery.attempt_recovery("ollama")
        assert recovery.is_fallback_active("ollama")
    finally:
        await dispose_container(ctx.container)


@pytest.mark.asyncio
async def test_boot_with_empty_datasets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty datasets directory completes discovery with zero datasets."""
    ctx = await boot_container(tmp_path, monkeypatch, llm_healthy=False)
    try:
        dataset_phase = phase_result(ctx.report, InitPhase.DATASET_DISCOVERY)
        assert dataset_phase.status is InitStatus.COMPLETED
        assert dataset_phase.details.get("total_discovered") == 0
        assert ctx.report.system_status in {
            SystemReadiness.READY,
            SystemReadiness.DEGRADED,
        }
    finally:
        await dispose_container(ctx.container)


@pytest.mark.asyncio
async def test_boot_with_no_forensic_libraries(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing pytsk3/volatility3 libraries degrade parser bootstrap and list parsers."""
    ctx = await boot_container(
        tmp_path,
        monkeypatch,
        llm_healthy=False,
        parsers_unavailable=True,
    )
    try:
        parser_phase = phase_result(ctx.report, InitPhase.FORENSIC_PARSERS)
        assert parser_phase.status is InitStatus.DEGRADED
        assert ctx.report.system_status is SystemReadiness.DEGRADED

        parsers = parser_phase.details.get("parsers", {})
        assert isinstance(parsers, dict) and parsers
        assert all(item.get("available") is False for item in parsers.values())
        assert any(
            item.get("library") in {"pytsk3", "volatility3", "Registry", "Evtx", "sqlite3"}
            for item in parsers.values()
        )
    finally:
        await dispose_container(ctx.container)
