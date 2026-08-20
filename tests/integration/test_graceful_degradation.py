"""Graceful degradation and recovery integration tests (Prompt 12.14)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest
from dfat.bootstrap.models import SystemReadiness
from dfat.case_management.enums import CaseStatus
from dfat.core.models.case import Case, CaseMetadata
from dfat.core.models.pipeline import StageResult
from dfat.pipeline.models import PipelineJob
from dfat.pipeline.stage_interface import PipelineContext
from tests.integration.boot_helpers import (
    boot_container,
    dispose_container,
    patch_llm_health,
)


@pytest.mark.asyncio
async def test_system_degrades_not_crashes(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    sample_artefact_set,
) -> None:
    """Optional services disabled: system stays DEGRADED but core workflows still run."""
    ctx = await boot_container(
        tmp_path,
        monkeypatch,
        llm_healthy=False,
        parsers_unavailable=True,
    )
    try:
        assert ctx.report.system_status is SystemReadiness.DEGRADED

        user_repo = ctx.container.repositories.user_repo()
        admin = await user_repo.get_by_username("admin")
        assert admin is not None

        case_repo = ctx.container.repositories.case_repo()
        case = Case(
            metadata=CaseMetadata(
                case_id="case-degraded-001",
                case_name="Degraded Mode Case",
                investigator="Admin",
            ),
            status=CaseStatus.CREATED,
            lead_investigator_id=admin.id,
        )
        await case_repo.save(case, created_by_user_id=admin.id)
        loaded = await case_repo.get(case.case_id)
        assert loaded is not None

        triage_stage = ctx.container.pipeline.triage_stage()
        job = PipelineJob(
            evidence_id=sample_artefact_set.evidence_id,
            case_id=case.case_id,
            user_id=admin.id,
            mode="full",
            use_fallback_analyzer=True,
        )
        context = PipelineContext(job=job, artefact_set=sample_artefact_set)
        result: StageResult = await triage_stage.execute(context)

        assert result.success is True
        assert context.ranked_artefacts
        assert context.metadata.get("triage_source") in {
            "rule_engine+fallback_summary",
            "fallback_analyzer",
            "rule_engine",
        }
    finally:
        await dispose_container(ctx.container)


@pytest.mark.asyncio
async def test_recovery_after_ollama_restart(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    sample_artefact_set,
) -> None:
    """Health monitoring detects Ollama recovery; the next triage run can use the LLM."""
    ctx = await boot_container(tmp_path, monkeypatch, llm_healthy=False)
    try:
        assert ctx.report.system_status is SystemReadiness.DEGRADED

        recovery = ctx.container.recovery_manager()
        await recovery.attempt_recovery("ollama")
        assert recovery.is_fallback_active("ollama")

        monitor = ctx.container.service_monitor()
        unhealthy = await monitor.check_service("ollama")
        assert unhealthy.is_healthy is False

        patch_llm_health(ctx.container, monkeypatch, healthy=True)
        healthy = await monitor.check_service("ollama")
        assert healthy.is_healthy is True

        llm = MagicMock()
        llm.is_available = MagicMock(return_value=True)
        from dfat.core.enums import SuspicionLevel
        from dfat.core.models.artefact import RankedArtefact

        ranked = [
            RankedArtefact(
                **sample_artefact_set.artefacts[0].model_dump(),
                suspicion_level=SuspicionLevel.MEDIUM,
                relevance_score=0.75,
                classification_reasoning="LLM after recovery",
            )
        ]
        llm.analyze = MagicMock(return_value=ranked)
        llm.summarize = MagicMock(return_value="Recovered LLM summary")

        triage_stage = ctx.container.pipeline.triage_stage()
        triage_stage._llm = llm  # noqa: SLF001 — integration override for recovery scenario
        triage_stage._fallback = ctx.container.ai_engine.fallback()

        job = PipelineJob(
            evidence_id=sample_artefact_set.evidence_id,
            case_id="case-recovery",
            user_id="user-recovery",
            mode="full",
            use_fallback_analyzer=False,
        )
        context = PipelineContext(job=job, artefact_set=sample_artefact_set)
        result: StageResult = await triage_stage.execute(context)

        assert result.success is True
        assert context.metadata.get("triage_source") == "llm"
        llm.analyze.assert_called_once()
    finally:
        await dispose_container(ctx.container)


@pytest.mark.asyncio
async def test_dataset_watcher_detects_new_files(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Background dataset watcher registers a file dropped after boot."""
    ctx = await boot_container(tmp_path, monkeypatch, llm_healthy=False)
    try:
        datasets_dir = ctx.settings.dataset_intelligence.datasets_dir
        datasets_dir.mkdir(parents=True, exist_ok=True)

        registry = ctx.container.dataset_intelligence.dataset_registry()
        task_manager = ctx.container.task_manager()

        initial = await registry.list_datasets()
        assert len(initial) == 0

        await task_manager.start_all()
        try:
            new_file = datasets_dir / "watcher-test.json"
            new_file.write_text(
                json.dumps({"dataset": "watcher-test", "records": [{"name": "sample"}]}),
                encoding="utf-8",
            )

            await asyncio.sleep(2.5)

            discovered = await registry.list_datasets()
            assert len(discovered) >= 1
            assert any("watcher-test" in dataset.name for dataset in discovered)
        finally:
            await task_manager.stop_all()
    finally:
        await dispose_container(ctx.container)
