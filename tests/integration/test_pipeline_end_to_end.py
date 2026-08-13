"""Integration tests for end-to-end pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

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
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.job_manager import JobManager
from dfat.pipeline.job_runner import JobRunner
from dfat.pipeline.orchestrator import PipelineOrchestrator
from dfat.pipeline.pipeline_logger import PipelineLogger
from dfat.pipeline.progress_tracker import ProgressTracker
from dfat.pipeline.stage_interface import IPipelineStage, PipelineContext
from dfat.pipeline.stage_registry import StageRegistry
from dfat.settings import DFATSettings


class _FakeStage(IPipelineStage):
    """Minimal stage stub that records success."""

    def __init__(self, stage: PipelineStage, hook=None) -> None:
        self._stage = stage
        self._hook = hook

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
            self._hook(context)
        return StageResult(
            stage=self._stage,
            success=True,
            duration_seconds=0.01,
            output_data={"ok": True},
            errors=[],
        )


def _report_for(evidence: EvidenceImage, case: CaseMetadata) -> ForensicReport:
    """Build a minimal dual-output report for tests."""
    json_layer = JSONReport(
        evidence_id=evidence.evidence_id,
        artefact_data=[],
        integrity_hash="b" * 64,
    )
    narrative = NarrativeReport(
        evidence_id=evidence.evidence_id,
        summary_text="Integration test summary",
        llm_model_used="test",
    )
    return ForensicReport(
        case=case,
        json_report=json_layer,
        narrative_report=narrative,
        stage_timings={
            "acquisition_s": 0.1,
            "parsing_s": 0.1,
            "triage_s": 0.1,
            "reporting_s": 0.1,
            "evaluation_s": 0.0,
        },
        pipeline_duration_seconds=0.4,
    )


def _pipeline(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    mock_audit_logger: MagicMock,
    artefact_set: ArtefactSet,
) -> tuple[PipelineOrchestrator, EvidenceImage]:
    """Build a PipelineOrchestrator with stubbed stages and repos."""
    evidence_path = tmp_path / "sample.dd"
    evidence_path.write_bytes(b"DFAT-E2E")
    evidence = EvidenceImage(
        evidence_id=artefact_set.evidence_id,
        file_path=evidence_path,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=evidence_path.stat().st_size,
        case=sample_case_metadata,
    )

    def _acquisition_hook(context: PipelineContext) -> None:
        context.evidence = evidence

    def _parsing_hook(context: PipelineContext) -> None:
        context.artefact_set = artefact_set

    def _triage_hook(context: PipelineContext) -> None:
        assert context.artefact_set is not None
        context.ranked_artefacts = [
            RankedArtefact(
                **item.model_dump(),
                suspicion_level=SuspicionLevel.MEDIUM,
                relevance_score=0.5,
                classification_reasoning="test",
            )
            for item in context.artefact_set.artefacts
        ]
        context.summary_text = "triaged"

    def _reporting_hook(context: PipelineContext) -> None:
        context.report = _report_for(evidence, sample_case_metadata)

    registry = StageRegistry()
    registry.register(_FakeStage(PipelineStage.ACQUISITION, _acquisition_hook))
    registry.register(_FakeStage(PipelineStage.PARSING, _parsing_hook))
    registry.register(_FakeStage(PipelineStage.AI_TRIAGE, _triage_hook))
    registry.register(_FakeStage(PipelineStage.REPORTING, _reporting_hook))
    registry.register(_FakeStage(PipelineStage.EVALUATION))

    audit = AsyncMock()
    audit.log_action = AsyncMock()
    job_manager = JobManager(audit_service=audit, max_concurrent=2)
    job_runner = JobRunner(
        job_manager=job_manager,
        stage_registry=registry,
        audit_service=audit,
    )
    progress = ProgressTracker()
    pipeline_logger = PipelineLogger(audit_service=audit, app_logger=MagicMock())

    evidence_repo = AsyncMock()
    evidence_repo.get.return_value = evidence
    case_repo = AsyncMock()
    case_repo.get.return_value = None

    evidence_mgmt = AsyncMock()
    custody = AsyncMock()
    custody.record_analysis = AsyncMock()

    orchestrator = PipelineOrchestrator(
        stage_registry=registry,
        job_manager=job_manager,
        job_runner=job_runner,
        progress_tracker=progress,
        pipeline_logger=pipeline_logger,
        evidence_repo=evidence_repo,
        case_repo=case_repo,
        audit_service=audit,
        settings=DFATSettings(),
        evidence_management_service=evidence_mgmt,
        custody_service=custody,
        ground_truth_loader=GroundTruthLoader(
            tmp_path,
            DFRWSHandler(tmp_path),
            CFReDSHandler(tmp_path),
        ),
        benchmark_comparator=BenchmarkComparator(
            metrics=MetricsCalculator(),
            ground_truth_loader=GroundTruthLoader(
                tmp_path,
                DFRWSHandler(tmp_path),
                CFReDSHandler(tmp_path),
            ),
            audit_service=AsyncMock(),
            benchmark_repo=AsyncMock(),
            thresholds={"precision_min": 0.0, "recall_min": 0.0, "f1_min": 0.0},
        ),
    )
    return orchestrator, evidence


@pytest.mark.asyncio
async def test_execute_pipeline_completes_all_stages(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify full pipeline runs all stages via the job runner."""
    orchestrator, evidence = _pipeline(
        tmp_path,
        sample_case_metadata,
        mock_audit_logger,
        sample_artefact_set,
    )

    job = await orchestrator.execute_pipeline(
        evidence_id=evidence.evidence_id,
        case_id=sample_case_metadata.case_id,
        user_id="user-1",
        mode="full",
        use_fallback=True,
    )

    assert job.status is JobStatus.COMPLETED
    report = orchestrator.get_job_report(job.job_id)
    assert report is not None
    assert report.report_id
    assert report.narrative_report.summary_text
    assert "acquisition_s" in report.stage_timings
    assert "parsing_s" in report.stage_timings
    assert "triage_s" in report.stage_timings
    assert "reporting_s" in report.stage_timings


@pytest.mark.asyncio
async def test_execute_pipeline_parse_only_returns_artefact_set(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify parse-only mode returns a normalised artefact set."""
    orchestrator, evidence = _pipeline(
        tmp_path,
        sample_case_metadata,
        mock_audit_logger,
        sample_artefact_set,
    )

    job = await orchestrator.execute_pipeline(
        evidence_id=evidence.evidence_id,
        case_id=sample_case_metadata.case_id,
        user_id="user-1",
        mode="parse-only",
    )

    assert job.status is JobStatus.COMPLETED
    artefact_set = orchestrator.get_job_artefact_set(job.job_id)
    assert artefact_set is not None
    assert artefact_set.total_count == sample_artefact_set.total_count


@pytest.mark.asyncio
async def test_execute_pipeline_triage_only_uses_cached_artefacts(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify triage-only mode ranks previously cached artefacts."""
    orchestrator, evidence = _pipeline(
        tmp_path,
        sample_case_metadata,
        mock_audit_logger,
        sample_artefact_set,
    )
    orchestrator._artefact_cache[evidence.evidence_id] = sample_artefact_set  # noqa: SLF001

    job = await orchestrator.execute_pipeline(
        evidence_id=evidence.evidence_id,
        case_id=sample_case_metadata.case_id,
        user_id="user-1",
        mode="triage-only",
        use_fallback=True,
    )

    assert job.status is JobStatus.COMPLETED
    context = orchestrator._job_contexts[job.job_id]  # noqa: SLF001
    assert context.ranked_artefacts is not None
    assert len(context.ranked_artefacts) == sample_artefact_set.total_count


@pytest.mark.asyncio
async def test_pipeline_state_marks_evaluation_stage(
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
    sample_artefact_set: ArtefactSet,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify full pipeline records all five stage results including evaluation."""
    orchestrator, evidence = _pipeline(
        tmp_path,
        sample_case_metadata,
        mock_audit_logger,
        sample_artefact_set,
    )

    job = await orchestrator.execute_pipeline(
        evidence_id=evidence.evidence_id,
        case_id=sample_case_metadata.case_id,
        user_id="user-1",
        mode="full",
        use_fallback=True,
    )
    state = orchestrator.get_pipeline_state(job.job_id)

    assert state is not None
    assert state.is_complete is True
    assert "evaluation" in state.stage_results
