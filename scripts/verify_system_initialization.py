#!/usr/bin/env python3
"""Verify Prompt 12 system initialization end-to-end.

Boots DFAT in an isolated temporary directory, asserts critical phases,
capabilities surface, optional test triage, and startup-report accuracy.
Prints PASS/FAIL and writes ``reports/system_initialization_verification.json``.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ok(results: list[str], condition: bool, message: str) -> bool:
    results.append(f"{'[PASS]' if condition else '[FAIL]'} {message}")
    return condition


async def _seed_role_users(container: Any) -> None:
    from dfat.database.models.user import UserORM

    user_repo = container.repositories.user_repo()
    hasher = container.auth.password_hasher()
    for role_name in ("investigator", "analyst", "viewer"):
        if await user_repo.get_by_username(role_name) is not None:
            continue
        role = await user_repo.get_role_by_name(role_name)
        if role is None:
            raise RuntimeError(f"Missing role: {role_name}")
        await user_repo.save(
            UserORM(
                id=str(uuid4()),
                username=role_name,
                email=f"{role_name}@verify.local",
                hashed_password=hasher.hash_password("VerifyPass123!"),
                full_name=role_name.title(),
                role_id=role.id,
                is_active=True,
                is_locked=False,
                failed_login_attempts=0,
            )
        )


async def boot_and_verify(tmp_path: Path, results: list[str]) -> dict[str, Any]:
    from unittest.mock import patch

    # Import container first to avoid bootstrap→services circular import on cold start.
    from dfat.container import build_application_container
    from dfat.ai_engine.llm.connection import LLMHealthStatus
    from dfat.bootstrap.boot_sequencer import BootSequencer
    from dfat.bootstrap.directory_manager import DirectoryManager
    from dfat.bootstrap.models import InitPhase, InitStatus, SystemReadiness
    from dfat.core.enums import ArtefactCategory
    from dfat.core.models.artefact import Artefact, ArtefactSet
    from dfat.database.engine import DatabaseEngine
    from dfat.pipeline.models import PipelineJob
    from dfat.pipeline.stage_interface import PipelineContext
    from dfat.settings import load_settings

    data = tmp_path / "data"
    db_path = data / "dfat.db"
    settings = load_settings(env="development")
    settings.database.url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    settings.logging.audit_log_path = data / "outputs" / "audit.log"
    settings.evidence.evidence_dir = data / "evidence"
    settings.reporting.output_dir = data / "outputs"
    settings.dataset_intelligence.datasets_dir = data / "datasets"
    settings.dataset_intelligence.vector_store_path = data / "knowledge" / "vector_store"
    settings.dataset_intelligence.knowledge_graph_path = data / "knowledge" / "graph"
    settings.dataset_intelligence.ioc_database_path = data / "knowledge" / "ioc_db"
    settings.ml.models_dir = data / "ml" / "models"
    settings.ml.experiments_dir = data / "ml" / "experiments"
    settings.auth.secret_key = "verify-system-init-secret-key-32chars!!"

    container = build_application_container()
    container.settings.override(settings)
    container.database.database_engine.override(
        DatabaseEngine(database_url=settings.database.url, echo=False)
    )
    container.bootstrap.directory_manager.override(DirectoryManager(base_dir=tmp_path))

    async def _healthy() -> LLMHealthStatus:
        return LLMHealthStatus(
            is_healthy=False,
            model_loaded=False,
            model_name="",
            response_time_ms=0.0,
            error="verification stub — ollama not required",
        )

    connection = container.ai_engine.connection_manager()
    connection.check_health = _healthy  # type: ignore[method-assign]

    original_run = BootSequencer._run_phase

    async def _run_with_seed(self, phase, runner, is_critical):  # type: ignore[no-untyped-def]
        result = await original_run(self, phase, runner, is_critical)
        if phase is InitPhase.DATABASE and result.status is InitStatus.COMPLETED:
            await _seed_role_users(container)
        return result

    report = None
    try:
        with patch.object(BootSequencer, "_run_phase", _run_with_seed):
            report = await container.boot_sequencer().boot()

        _ok(
            results,
            report.system_status
            in {SystemReadiness.READY, SystemReadiness.DEGRADED},
            f"System status is READY or DEGRADED ({report.system_status.value})",
        )
        _ok(results, len(report.phases) == 16, f"Boot reported {len(report.phases)} phases (expected 16)")
        _ok(results, report.completed_at is not None, "Startup report has completed_at")
        _ok(results, report.total_duration_ms >= 0, "Startup report duration is non-negative")

        critical = {
            InitPhase.CONFIGURATION,
            InitPhase.DIRECTORIES,
            InitPhase.DATABASE,
            InitPhase.AUTHENTICATION,
            InitPhase.AUDIT_LOGGING,
            InitPhase.REPORTING,
        }
        by_phase = {p.phase: p for p in report.phases}
        for phase in critical:
            item = by_phase.get(phase)
            _ok(
                results,
                item is not None and item.status is InitStatus.COMPLETED,
                f"Critical phase {phase.value} COMPLETED",
            )

        _ok(
            results,
            bool(report.available_capabilities),
            f"Available capabilities listed ({len(report.available_capabilities)})",
        )
        _ok(
            results,
            InitPhase.BACKGROUND_WORKERS in by_phase,
            "Background workers phase present",
        )

        registry = container.pipeline.parser_registry()
        parsers = registry.get_all_parsers()
        _ok(results, len(parsers) >= 1, f"Parser registry has {len(parsers)} parser(s)")

        if report.system_status in {SystemReadiness.READY, SystemReadiness.DEGRADED}:
            available = [p for p in parsers if registry.is_parser_available(p)]
            if available:
                triage = container.pipeline.triage_stage()
                artefacts = ArtefactSet(
                    evidence_id="ev-verify-init",
                    artefacts=[
                        Artefact(
                            artefact_id="art-verify-1",
                            category=ArtefactCategory.RUNNING_PROCESS,
                            source_evidence_id="ev-verify-init",
                            raw_data={"name": "notepad.exe", "pid": 100},
                        )
                    ],
                    categories_present=[ArtefactCategory.RUNNING_PROCESS],
                )
                job = PipelineJob(
                    evidence_id="ev-verify-init",
                    case_id="case-verify-init",
                    user_id="verify",
                    mode="full",
                    use_fallback_analyzer=True,
                )
                context = PipelineContext(job=job, artefact_set=artefacts)
                stage_result = await triage.execute(context)
                _ok(
                    results,
                    stage_result.success and bool(context.ranked_artefacts),
                    "Rule-based triage pipeline executed successfully",
                )
            else:
                _ok(
                    results,
                    True,
                    "Skipped live parser pipeline (no forensic libraries available) — expected in minimal env",
                )
        else:
            _ok(
                results,
                False,
                f"Skipped triage — boot status was {report.system_status.value}",
            )

        llm_phase = by_phase.get(InitPhase.LLM_SERVICE)
        if llm_phase is not None and llm_phase.status is InitStatus.DEGRADED:
            _ok(
                results,
                "llm_service" in (llm_phase.degraded_capabilities or [])
                or "llm" in llm_phase.message.lower()
                or "fallback" in llm_phase.message.lower(),
                "LLM degradation message documents fallback behaviour",
            )

        return {
            "system_status": report.system_status.value,
            "phases": [
                {
                    "phase": p.phase.value,
                    "status": p.status.value,
                    "message": p.message,
                }
                for p in report.phases
            ],
            "available_capabilities": list(report.available_capabilities),
            "degraded_services": list(report.degraded_services),
            "critical_failures": list(report.critical_failures),
        }
    finally:
        try:
            await container.database.database_engine().dispose()
        except Exception:  # noqa: BLE001
            pass


async def main() -> int:
    results: list[str] = []
    print("DFAT System Initialization Verification")
    print("=" * 72)

    payload: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="dfat-verify-init-") as tmp:
        try:
            payload = await boot_and_verify(Path(tmp), results)
        except Exception as exc:  # noqa: BLE001
            _ok(results, False, f"Boot verification raised: {exc}")

    for line in results:
        print(f"  {line}")

    passed = bool(results) and all(line.startswith("[PASS]") for line in results)
    summary = {
        "passed": passed,
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": results,
        "startup_report": payload,
    }
    reports = REPO_ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "system_initialization_verification.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print("=" * 72)
    print(f"OVERALL: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
