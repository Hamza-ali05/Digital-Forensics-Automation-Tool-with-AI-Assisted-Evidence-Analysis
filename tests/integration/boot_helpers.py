"""Shared helpers for Prompt 12.14 full-system boot integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

import pytest

from dfat.bootstrap.boot_sequencer import BootSequencer
from dfat.bootstrap.directory_manager import DirectoryManager
from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult, StartupReport, SystemReadiness
from dfat.bootstrap.parser_initializer import ParserInitializer
from dfat.container import ApplicationContainer, build_application_container
from dfat.database.engine import DatabaseEngine
from dfat.database.models.user import UserORM
from dfat.settings import DFATSettings, load_settings

CRITICAL_BOOT_PHASES: frozenset[InitPhase] = frozenset(
    {
        InitPhase.CONFIGURATION,
        InitPhase.DIRECTORIES,
        InitPhase.DATABASE,
        InitPhase.AUTHENTICATION,
        InitPhase.AUDIT_LOGGING,
        InitPhase.REPORTING,
    }
)


@dataclass
class BootContext:
    """Result of an isolated application boot for integration tests."""

    container: ApplicationContainer
    report: StartupReport
    settings: DFATSettings
    tmp_path: Path


def make_isolated_settings(tmp_path: Path, *, env: str = "development") -> DFATSettings:
    """Build settings with every data path rooted under ``tmp_path``."""
    data = tmp_path / "data"
    db_path = data / "dfat.db"
    settings = load_settings(env=env)
    settings.database.url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    settings.logging.audit_log_path = data / "outputs" / "audit.log"
    settings.evidence.evidence_dir = data / "evidence"
    settings.reporting.output_dir = data / "outputs"
    settings.dataset_intelligence.datasets_dir = data / "datasets"
    settings.dataset_intelligence.vector_store_path = data / "knowledge" / "vector_store"
    settings.dataset_intelligence.knowledge_graph_path = data / "knowledge" / "graph"
    settings.dataset_intelligence.ioc_database_path = data / "knowledge" / "ioc_db"
    settings.dataset_intelligence.watch_interval_seconds = 1
    settings.ml.models_dir = data / "ml" / "models"
    settings.ml.experiments_dir = data / "ml" / "experiments"
    settings.auth.secret_key = "test-secret-key-not-for-production"
    return settings


async def seed_role_users(container: ApplicationContainer) -> None:
    """Seed investigator/analyst/viewer users required by ``AuthInitializer``."""
    user_repo = container.repositories.user_repo()
    hasher = container.auth.password_hasher()
    for role_name in ("investigator", "analyst", "viewer"):
        existing = await user_repo.get_by_username(role_name)
        if existing is not None:
            continue
        role = await user_repo.get_role_by_name(role_name)
        if role is None:
            raise RuntimeError(f"Missing role seed: {role_name}")
        await user_repo.save(
            UserORM(
                id=str(uuid4()),
                username=role_name,
                email=f"{role_name}@example.com",
                hashed_password=hasher.hash_password("ProbePass123!"),
                full_name=role_name.title(),
                role_id=role.id,
                is_active=True,
                is_locked=False,
                failed_login_attempts=0,
            )
        )


def _patch_user_seed_after_database(
    monkeypatch: pytest.MonkeyPatch,
    container: ApplicationContainer,
) -> None:
    """Inject role-user seeding immediately after the DATABASE boot phase."""

    original_run = BootSequencer._run_phase

    async def _run_with_seed(
        self: BootSequencer,
        phase: InitPhase,
        runner: Callable[..., Any],
        is_critical: bool,
    ) -> PhaseResult:
        result = await original_run(self, phase, runner, is_critical)
        if phase is InitPhase.DATABASE and result.status is InitStatus.COMPLETED:
            await seed_role_users(container)
        return result

    monkeypatch.setattr(BootSequencer, "_run_phase", _run_with_seed)


def patch_llm_health(
    container: ApplicationContainer,
    monkeypatch: pytest.MonkeyPatch,
    *,
    healthy: bool,
    error: str = "connection refused",
) -> None:
    """Stub Ollama health checks for deterministic boot scenarios."""
    from dfat.ai_engine.llm.connection import LLMHealthStatus

    connection = container.ai_engine.connection_manager()

    async def _check_health() -> LLMHealthStatus:
        return LLMHealthStatus(
            is_healthy=healthy,
            model_loaded=healthy,
            model_name="llama3" if healthy else "",
            response_time_ms=12.0 if healthy else 0.0,
            error=None if healthy else error,
        )

    monkeypatch.setattr(connection, "check_health", _check_health)


def patch_all_parsers_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force forensic parser bootstrap into DEGRADED with an empty parser inventory."""

    def _always_unavailable(
        _self: ParserInitializer,
        _library_name: str,
    ) -> tuple[bool, Optional[str]]:
        return False, None

    monkeypatch.setattr(ParserInitializer, "_check_library", _always_unavailable)


def phase_result(report: StartupReport, phase: InitPhase) -> PhaseResult:
    """Return the ``PhaseResult`` for ``phase`` or raise ``AssertionError``."""
    for item in report.phases:
        if item.phase is phase:
            return item
    raise AssertionError(f"Phase {phase.value} not present in startup report")


def assert_critical_phases_completed(report: StartupReport) -> None:
    """Assert every critical bootstrap phase reached ``COMPLETED``."""
    for phase in CRITICAL_BOOT_PHASES:
        result = phase_result(report, phase)
        assert result.status is InitStatus.COMPLETED, (
            f"Critical phase {phase.value} was {result.status.value}: "
            f"{result.error or result.message}"
        )


async def boot_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    env: str = "development",
    settings_overrides: Optional[dict[str, Any]] = None,
    llm_healthy: Optional[bool] = None,
    parsers_unavailable: bool = False,
    seed_users: bool = True,
) -> BootContext:
    """Boot DFAT in an isolated temporary environment."""
    settings = make_isolated_settings(tmp_path, env=env)
    if settings_overrides:
        for key, value in settings_overrides.items():
            setattr(settings, key, value)

    container = build_application_container()
    container.settings.override(settings)
    db_settings = settings.database
    container.database.database_engine.override(
        DatabaseEngine(
            database_url=db_settings.url,
            echo=db_settings.echo,
            pool_size=db_settings.pool_size,
            max_overflow=db_settings.max_overflow,
        )
    )
    container.bootstrap.directory_manager.override(DirectoryManager(base_dir=tmp_path))

    if seed_users:
        _patch_user_seed_after_database(monkeypatch, container)
    if llm_healthy is not None:
        patch_llm_health(container, monkeypatch, healthy=llm_healthy)
    if parsers_unavailable:
        patch_all_parsers_unavailable(monkeypatch)

    report = await container.boot_sequencer().boot()

    return BootContext(
        container=container,
        report=report,
        settings=settings,
        tmp_path=tmp_path,
    )


async def dispose_container(container: ApplicationContainer) -> None:
    """Release database connections opened during boot."""
    try:
        engine = container.database.database_engine()
        await engine.dispose()
    except Exception:  # noqa: BLE001 — best-effort test cleanup
        pass


def assert_system_ready_or_degraded(report: StartupReport) -> None:
    """Assert overall readiness is ``READY`` or ``DEGRADED`` (not ``UNAVAILABLE``)."""
    assert report.system_status in {
        SystemReadiness.READY,
        SystemReadiness.DEGRADED,
    }
