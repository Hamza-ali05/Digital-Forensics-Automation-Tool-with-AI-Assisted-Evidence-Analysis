"""Full pipeline flow integration tests with mocked forensic libraries (Prompt 9.4)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.case_management.enums import EvidenceStatus
from dfat.core.enums import EvidenceType, HashAlgorithm, PipelineStage, SuspicionLevel
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.pipeline import StageResult
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.evaluation.benchmark.cfreds_handler import CFReDSHandler
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.dfrws_handler import DFRWSHandler
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.pipeline.enums import JobStatus, StageStatus
from dfat.pipeline.job_manager import JobManager
from dfat.pipeline.job_runner import JobRunner
from dfat.pipeline.orchestrator import PipelineOrchestrator
from dfat.pipeline.pipeline_logger import PipelineLogger
from dfat.pipeline.progress_tracker import ProgressTracker
from dfat.pipeline.stage_interface import IPipelineStage, PipelineContext
from dfat.pipeline.stage_registry import StageRegistry
from dfat.settings import DFATSettings


class _FakeStage(IPipelineStage):
    """Stage stub that optionally runs a hook and returns a configurable result."""

    def __init__(
        self,
        stage: PipelineStage,
        hook=None,
        *,
        success: bool = True,
        errors: list[str] | None = None,
        output_data: dict | None = None,
    ) -> None:
        self._stage = stage
        self._hook = hook
        self._success = success
        self._errors = list(errors or [])
        self._output_data = dict(output_data or {"ok": True})

    @property
    def stage_name(self) -> PipelineStage:
        return self._stage

    @property
    def description(self) -> str:
        return f"Fake {self._stage.value} stage"

    async def validate_preconditions(self, context: PipelineContext) -> bool:
        return True

    async def execute(self, context: PipelineContext) -> StageResult:
        if self._hook is not None:
            maybe = self._hook(context)
            if maybe is not None and hasattr(maybe, "__await__"):
                await maybe
        return StageResult(
            stage=self._stage,
            success=self._success,
            duration_seconds=0.01,
            output_data=self._output_data,
            errors=list(self._errors),
        )


def _report_for(evidence: EvidenceImage, case: CaseMetadata) -> ForensicReport:
    return ForensicReport(
        case=case,
        json_report=JSONReport(
            evidence_id=evidence.evidence_id,
            artefact_data=[],
            integrity_hash="b" * 64,
        ),
        narrative_report=NarrativeReport(
            evidence_id=evidence.evidence_id,
            summary_text="Full pipeline flow summary",
            llm_model_used="RuleBasedFallback",
        ),
        stage_timings={
            "acquisition_s": 0.1,
            "parsing_s": 0.1,
            "triage_s": 0.1,
            "reporting_s": 0.1,
            "evaluation_s": 0.0,
        },
        pipeline_duration_seconds=0.4,
    )


def _build_pipeline(
    *,
    tmp_path: Path,
    case: CaseMetadata,
    artefact_set: ArtefactSet,
    evidence_type: EvidenceType = EvidenceType.DISK_IMAGE,
    parsing_errors: list[str] | None = None,
    use_llm_fallback_hook: bool = False,
    cancel_after_parsing: bool = False,
) -> tuple[PipelineOrchestrator, EvidenceImage, AsyncMock, AsyncMock, JobManager]:
    """Build orchestrator with FakeStages and mocked custody / status services."""
    suffix = ".raw" if evidence_type is EvidenceType.MEMORY_DUMP else ".dd"
    evidence_path = tmp_path / f"sample{suffix}"
    evidence_path.write_bytes(b"DFAT-FULL-FLOW")
    evidence = EvidenceImage(
        evidence_id=artefact_set.evidence_id,
        file_path=evidence_path,
        evidence_type=evidence_type,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=evidence_path.stat().st_size,
        case=case,
    )

    def _acquisition(context: PipelineContext) -> None:
        context.evidence = evidence

    def _parsing(context: PipelineContext) -> None:
        context.artefact_set = artefact_set
        if parsing_errors:
            context.metadata["parser_warnings"] = list(parsing_errors)

    def _triage(context: PipelineContext) -> None:
        assert context.artefact_set is not None
        if use_llm_fallback_hook:
            context.metadata["analyzer_mode"] = "rule_based_fallback"
        context.ranked_artefacts = [
            RankedArtefact(
                **item.model_dump(),
                suspicion_level=SuspicionLevel.MEDIUM,
                relevance_score=0.5,
                classification_reasoning="flow-test",
            )
            for item in context.artefact_set.artefacts
        ]
        context.summary_text = "triaged via fallback" if use_llm_fallback_hook else "triaged"

    def _reporting(context: PipelineContext) -> None:
        context.report = _report_for(evidence, case)

    registry = StageRegistry()
    registry.register(_FakeStage(PipelineStage.ACQUISITION, _acquisition))
    registry.register(
        _FakeStage(
            PipelineStage.PARSING,
            _parsing,
            errors=parsing_errors,
            output_data={
                "ok": True,
                "warnings": list(parsing_errors or []),
                "partial": bool(parsing_errors),
            },
        )
    )
    registry.register(_FakeStage(PipelineStage.AI_TRIAGE, _triage))
    registry.register(_FakeStage(PipelineStage.REPORTING, _reporting))
    registry.register(_FakeStage(PipelineStage.EVALUATION))

    audit = AsyncMock()
    audit.log_action = AsyncMock()
    job_manager = JobManager(audit_service=audit, max_concurrent=2)
    job_runner = JobRunner(job_manager, registry, audit)
    evidence_repo = AsyncMock()
    evidence_repo.get = AsyncMock(return_value=evidence)
    evidence_mgmt = AsyncMock()
    evidence_mgmt.transition_evidence_status = AsyncMock()
    custody = AsyncMock()
    custody.record_analysis = AsyncMock()

    if cancel_after_parsing:
        original_update_stage = job_manager.update_stage

        async def _cancel_after_parse(job_id, stage, execution):
            await original_update_stage(job_id, stage, execution)
            if (
                stage is PipelineStage.PARSING
                and execution.status is StageStatus.COMPLETED
            ):
                await job_manager.update_job_status(job_id, JobStatus.CANCELLED)

        job_manager.update_stage = _cancel_after_parse  # type: ignore[method-assign]

    orchestrator = PipelineOrchestrator(
        stage_registry=registry,
        job_manager=job_manager,
        job_runner=job_runner,
        progress_tracker=ProgressTracker(),
        pipeline_logger=PipelineLogger(audit_service=audit, app_logger=MagicMock()),
        evidence_repo=evidence_repo,
        case_repo=AsyncMock(),
        audit_service=audit,
        settings=DFATSettings(),
        evidence_management_service=evidence_mgmt,
        custody_service=custody,
        ground_truth_loader=GroundTruthLoader(
            tmp_path, DFRWSHandler(tmp_path), CFReDSHandler(tmp_path)
        ),
        benchmark_comparator=BenchmarkComparator(
            metrics=MetricsCalculator(),
            ground_truth_loader=GroundTruthLoader(
                tmp_path, DFRWSHandler(tmp_path), CFReDSHandler(tmp_path)
            ),
            audit_service=AsyncMock(),
            benchmark_repo=AsyncMock(),
            thresholds={"precision_min": 0.0, "recall_min": 0.0, "f1_min": 0.0},
        ),
    )
    return orchestrator, evidence, evidence_mgmt, custody, job_manager


async def _assert_success_flow(
    orchestrator: PipelineOrchestrator,
    evidence: EvidenceImage,
    case: CaseMetadata,
    evidence_mgmt: AsyncMock,
    custody: AsyncMock,
    *,
    use_fallback: bool = False,
) -> None:
    job = await orchestrator.execute_pipeline(
        evidence_id=evidence.evidence_id,
        case_id=case.case_id,
        user_id="user-1",
        mode="full",
        use_fallback=use_fallback,
    )
    assert job.status is JobStatus.COMPLETED
    artefacts = orchestrator.get_job_artefact_set(job.job_id)
    assert artefacts is not None
    assert artefacts.total_count >= 1
    report = orchestrator.get_job_report(job.job_id)
    assert report is not None
    assert report.report_id
    evidence_mgmt.transition_evidence_status.assert_awaited()
    assert (
        evidence_mgmt.transition_evidence_status.await_args.args[1]
        is EvidenceStatus.PROCESSED
    )
    custody.record_analysis.assert_awaited()


@pytest.mark.asyncio
async def test_full_pipeline_disk_image(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
) -> None:
    """Register-style disk evidence → full pipeline → artefacts, report, PROCESSED, ANALYSED."""
    orchestrator, evidence, evidence_mgmt, custody, _ = _build_pipeline(
        tmp_path=tmp_path,
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        evidence_type=EvidenceType.DISK_IMAGE,
    )
    await _assert_success_flow(
        orchestrator, evidence, sample_case_metadata, evidence_mgmt, custody
    )


@pytest.mark.asyncio
async def test_full_pipeline_memory_dump(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
) -> None:
    """Same full-pipeline assertions for memory dump evidence."""
    orchestrator, evidence, evidence_mgmt, custody, _ = _build_pipeline(
        tmp_path=tmp_path,
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        evidence_type=EvidenceType.MEMORY_DUMP,
    )
    await _assert_success_flow(
        orchestrator, evidence, sample_case_metadata, evidence_mgmt, custody
    )


@pytest.mark.asyncio
async def test_pipeline_with_parser_failure(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
) -> None:
    """One parser fails but stage succeeds with warnings and partial artefacts."""
    warnings = ["FileSystemParser failed: corrupt partition table"]
    orchestrator, evidence, evidence_mgmt, custody, _ = _build_pipeline(
        tmp_path=tmp_path,
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        parsing_errors=warnings,
    )

    job = await orchestrator.execute_pipeline(
        evidence_id=evidence.evidence_id,
        case_id=sample_case_metadata.case_id,
        user_id="user-1",
        mode="full",
    )

    assert job.status is JobStatus.COMPLETED
    parsing = job.stage_executions.get(PipelineStage.PARSING.value)
    assert parsing is not None
    assert parsing.status is StageStatus.COMPLETED
    assert parsing.errors == warnings
    assert parsing.output_summary.get("partial") is True
    artefacts = orchestrator.get_job_artefact_set(job.job_id)
    assert artefacts is not None and artefacts.total_count >= 1
    evidence_mgmt.transition_evidence_status.assert_awaited()
    custody.record_analysis.assert_awaited()


@pytest.mark.asyncio
async def test_pipeline_with_llm_failure(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
) -> None:
    """LLM unavailable → rule-based fallback → report still generated."""
    orchestrator, evidence, evidence_mgmt, custody, _ = _build_pipeline(
        tmp_path=tmp_path,
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        use_llm_fallback_hook=True,
    )

    job = await orchestrator.execute_pipeline(
        evidence_id=evidence.evidence_id,
        case_id=sample_case_metadata.case_id,
        user_id="user-1",
        mode="full",
        use_fallback=True,
    )

    assert job.status is JobStatus.COMPLETED
    assert job.use_fallback_analyzer is True
    context = orchestrator._job_contexts[job.job_id]  # noqa: SLF001
    assert context.metadata.get("analyzer_mode") == "rule_based_fallback"
    report = orchestrator.get_job_report(job.job_id)
    assert report is not None
    assert report.narrative_report.summary_text
    evidence_mgmt.transition_evidence_status.assert_awaited()
    custody.record_analysis.assert_awaited()


@pytest.mark.asyncio
async def test_pipeline_cancellation(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
) -> None:
    """Cancel mid-parsing → CANCELLED status with partial artefacts retained."""
    orchestrator, evidence, _evidence_mgmt, _custody, _manager = _build_pipeline(
        tmp_path=tmp_path,
        case=sample_case_metadata,
        artefact_set=sample_artefact_set,
        cancel_after_parsing=True,
    )

    job = await orchestrator.execute_pipeline(
        evidence_id=evidence.evidence_id,
        case_id=sample_case_metadata.case_id,
        user_id="user-1",
        mode="full",
    )

    assert job.status is JobStatus.CANCELLED
    assert PipelineStage.PARSING.value in job.stage_executions
    assert PipelineStage.AI_TRIAGE.value not in job.stage_executions
    artefacts = orchestrator.get_job_artefact_set(job.job_id)
    assert artefacts is not None
    assert artefacts.total_count == sample_artefact_set.total_count
