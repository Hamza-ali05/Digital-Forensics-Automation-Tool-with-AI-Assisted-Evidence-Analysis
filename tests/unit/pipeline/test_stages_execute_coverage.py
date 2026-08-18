"""Execute-path coverage for pipeline stages and helper modules."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from dfat.case_management.enums import EvidenceStatus
from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm, PipelineStage
from dfat.core.exceptions import EvidenceNotFoundError
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.pipeline import StageResult
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.core.enums import SuspicionLevel
from dfat.evidence_management.exceptions import InvalidEvidenceTransitionError
from dfat.evidence_management.models import HashSet
from dfat.pipeline.enums import JobStatus, ParserStatus, StageStatus
from dfat.pipeline.error_handler import PipelineErrorHandler
from dfat.pipeline.evidence_discovery import EvidenceDiscoveryService
from dfat.pipeline.evidence_loader import EvidenceLoader, LoadedEvidence
from dfat.pipeline.exceptions import (
    AllParsersFailedError,
    ParserUnavailableError,
    PipelineCancelledError,
    PipelineJobNotFoundError,
    PipelineStageError,
    PipelineTimeoutError,
)
from dfat.pipeline.models import ParserResult, PipelineJob, StageExecution
from dfat.pipeline.parser_registry import ParserRegistry
from dfat.pipeline.pipeline_logger import PipelineLogger
from dfat.pipeline.progress_tracker import ProgressNotFoundError
from dfat.pipeline.stage_interface import PipelineContext
from dfat.pipeline.stages.acquisition_stage import AcquisitionStage
from dfat.pipeline.stages.evaluation_stage import EvaluationStage
from dfat.pipeline.stages.parsing_stage import ParsingStage
from dfat.pipeline.stages.reporting_stage import ReportingStage
from dfat.pipeline.stages.triage_stage import TriageStage
from dfat.settings import EvidenceSettings


def _job(**kwargs) -> PipelineJob:
    base = dict(
        job_id=str(uuid4()),
        evidence_id="ev-1",
        case_id="case-1",
        user_id="user-1",
        status=JobStatus.RUNNING,
        mode="full",
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )
    base.update(kwargs)
    return PipelineJob(**base)


def _ctx(**kwargs) -> PipelineContext:
    base = {"job": _job(), "metadata": {}, "stage_timings": {}}
    base.update(kwargs)
    return PipelineContext(**base)


def _evidence(tmp_path: Path) -> EvidenceImage:
    path = tmp_path / "disk.E01"
    path.write_bytes(b"x" * 32)
    return EvidenceImage(
        evidence_id="ev-1",
        file_path=path,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=32,
        acquired_at=datetime.now(UTC),
        case=CaseMetadata(case_id="case-1", case_name="C", investigator="I"),
    )


def _artefact(evidence_id: str = "ev-1") -> Artefact:
    return Artefact(
        artefact_id=str(uuid4()),
        category=ArtefactCategory.FILESYSTEM_METADATA,
        source_evidence_id=evidence_id,
        raw_data={"path": "/a"},
        parsed_at=datetime.now(UTC),
    )


def _artefact_set(evidence_id: str = "ev-1") -> ArtefactSet:
    art = _artefact(evidence_id)
    return ArtefactSet(
        evidence_id=evidence_id,
        artefacts=[art],
        categories_present=[ArtefactCategory.FILESYSTEM_METADATA],
    )


def _progress() -> MagicMock:
    progress = MagicMock()
    progress.get_progress = MagicMock(side_effect=ProgressNotFoundError("missing"))
    progress.start_job = MagicMock()
    progress.start_stage = MagicMock()
    progress.complete_stage = MagicMock()
    progress.start_parser = MagicMock()
    progress.complete_parser = MagicMock()
    progress.fail_parser = MagicMock()
    return progress


def _hash_set() -> HashSet:
    return HashSet(
        md5="0" * 32,
        sha1="1" * 40,
        sha256="a" * 64,
        file_size_bytes=32,
    )


# --- AcquisitionStage ---


@pytest.mark.asyncio
async def test_acquisition_stage_success_and_failure(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    loader = AsyncMock()
    loaded = LoadedEvidence(
        evidence=evidence,
        evidence_type=EvidenceType.DISK_IMAGE,
        handler_context={"img_info": object()},
        integrity_verified=True,
    )
    loader.load_evidence = AsyncMock(return_value=loaded)
    mgmt = AsyncMock()
    mgmt.get_evidence_detail = AsyncMock(return_value={"evidence": evidence})
    mgmt.verify_evidence = AsyncMock(
        return_value={
            "integrity_verified": True,
            "hash_set": _hash_set().model_dump(mode="json"),
            "custody_record": MagicMock(),
        }
    )
    mgmt.transition_evidence_status = AsyncMock()
    custody = AsyncMock()
    progress = _progress()
    audit = AsyncMock()
    stage = AcquisitionStage(loader, mgmt, custody, progress, audit)

    ctx = _ctx()
    assert await stage.validate_preconditions(ctx) is True
    assert stage.stage_name is PipelineStage.ACQUISITION
    assert "Acquire" in stage.description

    result = await stage.execute(ctx)
    assert result.success is True
    assert ctx.evidence is evidence

    # no custody_record → record_access
    mgmt.verify_evidence = AsyncMock(
        return_value={"integrity_verified": True, "hash_set": None, "custody_record": None}
    )
    await stage.execute(_ctx())
    custody.record_access.assert_awaited()

    # integrity failure path
    mgmt.verify_evidence = AsyncMock(
        return_value={
            "integrity_verified": False,
            "discrepancies": {"sha256": {"expected": "a", "actual": "b"}},
        }
    )
    failed = await stage.execute(_ctx())
    assert failed.success is False

    # already PROCESSING transition
    mgmt.verify_evidence = AsyncMock(
        return_value={
            "integrity_verified": True,
            "hash_set": {"bad": True},
            "custody_record": MagicMock(),
        }
    )
    mgmt.transition_evidence_status = AsyncMock(
        side_effect=InvalidEvidenceTransitionError(
            "bad",
            current_status=EvidenceStatus.PROCESSING.value,
            attempted_status=EvidenceStatus.PROCESSING.value,
        )
    )
    mgmt.get_evidence_detail = AsyncMock(
        side_effect=[
            {"evidence": evidence},
            {"status": EvidenceStatus.PROCESSING},
        ]
    )
    ok = await stage.execute(_ctx())
    assert ok.success is True


# --- ParsingStage ---


@pytest.mark.asyncio
async def test_parsing_stage_success_and_all_failed(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    registry = ParserRegistry()
    router = MagicMock()
    parser = MagicMock()
    parser.parser_name = "FileSystemParser"
    parser.supported_categories = MagicMock(
        return_value=[ArtefactCategory.FILESYSTEM_METADATA]
    )
    parser.parse = MagicMock(return_value=_artefact_set())
    router.route.return_value = [parser]
    normalizer = MagicMock()
    normalizer.normalize = MagicMock(return_value=_artefact_set())
    progress = _progress()
    # second get_progress succeeds after start_job
    progress.get_progress = MagicMock(
        side_effect=[ProgressNotFoundError("x"), MagicMock()]
    )
    errors = AsyncMock()
    errors.handle_stage_error = AsyncMock(
        return_value=StageExecution(stage=PipelineStage.PARSING, status=StageStatus.FAILED)
    )
    errors.should_abort_pipeline = MagicMock(return_value=True)
    errors.handle_parser_error = AsyncMock(
        return_value=ParserResult(
            parser_name="FileSystemParser",
            status=ParserStatus.FAILED,
            category=ArtefactCategory.FILESYSTEM_METADATA,
            error="boom",
        )
    )
    audit = AsyncMock()
    stage = ParsingStage(registry, router, normalizer, progress, errors, audit)

    ctx = _ctx(evidence=evidence)
    assert await stage.validate_preconditions(ctx) is True
    result = await stage.execute(ctx)
    assert result.success is True
    assert ctx.artefact_set is not None

    # no evidence
    empty = await stage.execute(_ctx(evidence=None))
    assert empty.success is False

    # all parsers fail
    parser.parse = MagicMock(side_effect=RuntimeError("parse fail"))
    failed = await stage.execute(_ctx(evidence=evidence))
    assert failed.success is False

    # primary category fallbacks
    assert (
        ParsingStage._primary_category(
            MagicMock(supported_categories=MagicMock(return_value=[])),
            EvidenceType.MEMORY_DUMP,
        )
        is ArtefactCategory.RUNNING_PROCESS
    )


# --- TriageStage ---


@pytest.mark.asyncio
async def test_triage_stage_success_fallback_and_error() -> None:
    progress = _progress()
    audit = AsyncMock()
    settings = MagicMock()
    settings.pipeline = MagicMock(
        enable_artefact_correlation=True,
        enable_timeline_generation=True,
        enable_ioc_detection=True,
    )
    ioc = MagicMock(detect=MagicMock(return_value=[]))
    scoring = MagicMock()
    rule = MagicMock(evaluate=MagicMock(return_value=[]))
    aggregator = MagicMock()
    aggregator.aggregate = MagicMock(
        return_value=MagicMock(model_dump=MagicMock(return_value={"ok": True}))
    )
    llm = MagicMock()
    llm.is_available = MagicMock(return_value=True)
    ranked = [
        RankedArtefact(
            artefact_id="r1",
            category=ArtefactCategory.FILESYSTEM_METADATA,
            source_evidence_id="ev-1",
            raw_data={},
            suspicion_level=SuspicionLevel.HIGH,
            relevance_score=0.9,
        )
    ]
    llm.analyze = MagicMock(return_value=ranked)
    llm.summarize = MagicMock(return_value="summary")
    fallback = MagicMock()
    fallback.analyze = MagicMock(return_value=ranked)
    fallback.summarize = MagicMock(return_value="fb summary")

    categoriser = MagicMock(categorise=MagicMock(side_effect=lambda s: s))
    standardiser = MagicMock(standardise=MagicMock(side_effect=lambda s: s))
    deduplicator = MagicMock(deduplicate=MagicMock(side_effect=lambda s: s))
    correlator = MagicMock(correlate=MagicMock(side_effect=lambda s: s))
    mapper = MagicMock(
        build_map=MagicMock(return_value=MagicMock(total_relationships=1))
    )
    timeline = MagicMock(
        generate=MagicMock(
            return_value=MagicMock(entries=[], windows=[], earliest=None, latest=None)
        )
    )

    stage = TriageStage(
        ioc,
        scoring,
        rule,
        aggregator,
        llm,
        fallback,
        progress,
        audit,
        settings,
        categoriser=categoriser,
        standardiser=standardiser,
        deduplicator=deduplicator,
        correlator=correlator,
        relationship_mapper=mapper,
        timeline_generator=timeline,
    )
    aset = _artefact_set()
    ctx = _ctx(artefact_set=aset, evidence=None)
    assert await stage.validate_preconditions(ctx) is True
    result = await stage.execute(ctx)
    assert result.success is True
    assert ctx.summary_text == "summary"

    # forced fallback
    ctx2 = _ctx(artefact_set=aset, job=_job(use_fallback_analyzer=True))
    await stage.execute(ctx2)

    # llm failure → fallback
    llm.analyze = MagicMock(side_effect=RuntimeError("llm down"))
    await stage.execute(_ctx(artefact_set=aset))

    # missing artefact set
    missing = await stage.execute(_ctx(artefact_set=None))
    assert missing.success is False

    # processing exception
    categoriser.categorise = MagicMock(side_effect=RuntimeError("boom"))
    failed = await stage.execute(_ctx(artefact_set=aset))
    assert failed.success is False

    assert "No artefacts" in TriageStage._default_summary([])
    assert "critical" in TriageStage._default_summary(ranked).lower() or "Triage" in TriageStage._default_summary(ranked)


# --- ReportingStage ---


@pytest.mark.asyncio
async def test_reporting_stage_success_and_error(tmp_path: Path) -> None:
    progress = _progress()
    audit = AsyncMock()
    report = ForensicReport(
        report_id="rep-1",
        case=CaseMetadata(case_id="c", case_name="C", investigator="I"),
        json_report=JSONReport(
            report_id="j", evidence_id="ev-1", artefact_data=[], integrity_hash="c" * 64
        ),
        narrative_report=NarrativeReport(
            report_id="n",
            evidence_id="ev-1",
            summary_text="s",
            llm_model_used="m",
        ),
        pipeline_duration_seconds=1.0,
    )
    builder = MagicMock()
    builder.build_complete_report = MagicMock(return_value=report)
    stage = ReportingStage(builder, progress, audit)
    aset = _artefact_set()
    ranked = [
        RankedArtefact(
            category=ArtefactCategory.FILESYSTEM_METADATA,
            source_evidence_id="ev-1",
            raw_data={},
            suspicion_level=SuspicionLevel.LOW,
            relevance_score=0.1,
        )
    ]
    ctx = _ctx(
        artefact_set=aset,
        ranked_artefacts=ranked,
        summary_text="summary",
        evidence=_evidence(tmp_path),
    )
    assert await stage.validate_preconditions(ctx) is True
    result = await stage.execute(ctx)
    assert result.success is True
    assert ctx.report is report

    missing = await stage.execute(_ctx())
    assert missing.success is False

    builder.build_complete_report = MagicMock(side_effect=RuntimeError("build fail"))
    failed = await stage.execute(
        _ctx(artefact_set=aset, ranked_artefacts=ranked, summary_text="s")
    )
    assert failed.success is False

    # resolve case from metadata dict
    case = ReportingStage._resolve_case(
        _ctx(metadata={"case": {"case_name": "X", "investigator": "Y"}})
    )
    assert case.case_name == "X"
    fallback = ReportingStage._resolve_case(_ctx(metadata={}))
    assert fallback.investigator == "user-1"


# --- EvaluationStage ---


@pytest.mark.asyncio
async def test_evaluation_stage_skip_success_and_fail(tmp_path: Path) -> None:
    progress = _progress()
    audit = AsyncMock()
    comparator = AsyncMock()
    comparator.compare = AsyncMock(
        return_value=MagicMock(
            model_dump=MagicMock(return_value={"f1": 1.0}),
            precision=1.0,
            recall=1.0,
            f1_score=1.0,
        )
    )
    loader = MagicMock()
    gt = MagicMock(dataset_name="dfrws")
    loader.load = MagicMock(return_value=gt)
    settings = MagicMock()
    settings.evaluation = MagicMock(ground_truth_dir=str(tmp_path))
    stage = EvaluationStage(comparator, loader, progress, audit, settings)

    skipped = await stage.execute(_ctx())
    assert skipped.success is True
    assert skipped.output_data["status"] == StageStatus.SKIPPED.value

    gt_file = tmp_path / "truth.json"
    gt_file.write_text("{}")
    ctx = _ctx(
        artefact_set=_artefact_set(),
        metadata={"ground_truth_path": str(gt_file)},
    )
    done = await stage.execute(ctx)
    assert done.success is True

    # missing artefact set with gt configured
    bad = await stage.execute(
        _ctx(artefact_set=None, metadata={"ground_truth_path": str(gt_file)})
    )
    assert bad.success is False

    comparator.compare = AsyncMock(side_effect=RuntimeError("cmp fail"))
    failed = await stage.execute(
        _ctx(artefact_set=_artefact_set(), metadata={"ground_truth_path": str(gt_file)})
    )
    assert failed.success is False

    # dataset lookup
    ds = tmp_path / "dfrws"
    ds.mkdir()
    (ds / "sample.json").write_text("{}")
    found = stage._find_dataset_file("sample")
    assert found is not None
    assert stage._resolve_ground_truth_path(_ctx(metadata={"ground_truth_dataset": "sample"}))
    assert stage._resolve_ground_truth_path(
        _ctx(metadata={"ground_truth_path": str(tmp_path / "missing.json")})
    ) is None


# --- helpers: discovery, loader, registry, logger, errors, exceptions ---


@pytest.mark.asyncio
async def test_evidence_discovery_and_loader(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    disk = evidence_dir / "sample.E01"
    disk.write_bytes(b"data")
    settings = EvidenceSettings(evidence_dir=evidence_dir)
    repo = AsyncMock()
    repo.list_all = AsyncMock(return_value=[])
    audit = AsyncMock()
    discovery = EvidenceDiscoveryService(settings, repo, audit)
    found = await discovery.discover()
    assert any(item.file_name == "sample.E01" for item in found)
    # registered skip
    repo.list_all = AsyncMock(
        return_value=[MagicMock(file_path=disk)]
    )
    assert await discovery.discover() == []
    datasets = await discovery.discover_in_dataset_dir()
    assert isinstance(datasets, list)

    # loader
    evidence = _evidence(tmp_path)
    disk_h = MagicMock()
    disk_h.open_image = MagicMock(return_value="img")
    disk_h.get_filesystem = MagicMock(return_value="fs")
    disk_h.close_image = MagicMock()
    mem_h = MagicMock()
    mem_h.validate_dump = MagicMock(return_value=True)
    mem_h.get_volatility_context = MagicMock(return_value="ctx")
    integrity = MagicMock(verify_integrity=MagicMock(return_value=True))
    hash_svc = MagicMock(verify_hash_set=MagicMock(return_value=True))
    loader = EvidenceLoader(disk_h, mem_h, integrity, hash_svc, audit)
    loaded = await loader.load_evidence(evidence, hash_set=_hash_set())
    assert loaded.integrity_verified is True
    await loader.unload_evidence(loaded)

    mem = evidence.model_copy(update={"evidence_type": EvidenceType.MEMORY_DUMP})
    mem_loaded = await loader.load_evidence(mem)
    assert "volatility_context" in mem_loaded.handler_context

    with pytest.raises(EvidenceNotFoundError):
        await loader.load_evidence(
            evidence.model_copy(update={"file_path": tmp_path / "missing.dd"})
        )


def test_parser_registry_deep() -> None:
    reg = ParserRegistry()
    parser = MagicMock()
    parser.parser_name = "FileSystemParser"
    parser.supported_evidence_types = MagicMock(return_value=[EvidenceType.DISK_IMAGE])
    parser.is_available = MagicMock(return_value=True)
    reg.register(parser)
    assert reg.get_parsers_for_type(EvidenceType.DISK_IMAGE) == [parser]
    assert reg.get_parser_by_name("FileSystemParser") is parser
    assert reg.check_availability()["FileSystemParser"] is True

    broken = MagicMock()
    broken.parser_name = "Broken"
    broken.supported_evidence_types = MagicMock(return_value=[EvidenceType.DISK_IMAGE])
    broken.is_available = MagicMock(side_effect=RuntimeError("x"))
    reg.register(broken)
    assert reg.is_parser_available(broken) is False

    no_checker = MagicMock(spec=["parser_name", "supported_evidence_types"])
    no_checker.parser_name = "Custom"
    no_checker.supported_evidence_types = MagicMock(return_value=[EvidenceType.DISK_IMAGE])
    with patch("dfat.pipeline.parser_registry.importlib.import_module", side_effect=ImportError):
        assert reg.is_parser_available(no_checker) is False


@pytest.mark.asyncio
async def test_pipeline_logger_and_error_handler() -> None:
    audit = AsyncMock()
    app_log = MagicMock()
    logger = PipelineLogger(audit, app_log)
    job = _job(current_stage=PipelineStage.PARSING, total_duration_seconds=1.0)
    await logger.log_job_start(job)
    await logger.log_stage_start(job.job_id, PipelineStage.PARSING)
    await logger.log_stage_complete(job.job_id, PipelineStage.PARSING, 1.0, 2)
    await logger.log_parser_start(job.job_id, "p")
    await logger.log_parser_complete(job.job_id, "p", 0.5, 1)
    await logger.log_parser_error(job.job_id, "p", "err")
    await logger.log_job_complete(job)
    await logger.log_job_failed(job, "fail")

    handler = PipelineErrorHandler(logger)
    pr = await handler.handle_parser_error(
        job.job_id,
        "FileSystemParser",
        ParserUnavailableError("x", parser_name="p", library_name="pytsk3"),
        EvidenceType.DISK_IMAGE,
    )
    assert pr.status is ParserStatus.UNAVAILABLE

    stage_exec = await handler.handle_stage_error(
        job.job_id,
        PipelineStage.PARSING,
        AllParsersFailedError("all", evidence_type=EvidenceType.DISK_IMAGE),
    )
    assert stage_exec.status is StageStatus.FAILED
    await handler.handle_stage_error(
        job.job_id, PipelineStage.AI_TRIAGE, RuntimeError("t")
    )
    await handler.handle_stage_error(
        job.job_id, PipelineStage.REPORTING, RuntimeError("r")
    )

    assert handler.should_abort_pipeline(PipelineStage.ACQUISITION, stage_exec) is True
    assert handler.should_abort_pipeline(PipelineStage.AI_TRIAGE, stage_exec) is False
    assert handler.should_abort_pipeline(PipelineStage.EVALUATION, stage_exec) is False
    assert handler.should_abort_pipeline(PipelineStage.REPORTING, stage_exec) is True

    completed = {
        "p": ParserResult(
            parser_name="p",
            status=ParserStatus.COMPLETED,
            artefacts_found=2,
            category=ArtefactCategory.FILESYSTEM_METADATA,
        )
    }
    partial = handler.assemble_partial_results(completed, "ev-1")
    assert partial is not None and partial.total_count == 2
    assert handler.assemble_partial_results({}, "ev") is None


def test_pipeline_exceptions() -> None:
    e1 = PipelineJobNotFoundError("missing", job_id="j1")
    assert e1.job_id == "j1"
    e2 = PipelineStageError(
        "stage",
        stage=PipelineStage.PARSING,
        original_error=RuntimeError("x"),
    )
    assert e2.stage is PipelineStage.PARSING
    e3 = PipelineTimeoutError(
        "timeout", stage=PipelineStage.PARSING, timeout_seconds=30.0
    )
    assert e3.timeout_seconds == 30.0
    e4 = PipelineCancelledError("cancelled", job_id="j1")
    assert e4.job_id == "j1"
    e5 = ParserUnavailableError("lib", parser_name="p", library_name="pytsk3")
    assert e5.library_name == "pytsk3"
    e6 = AllParsersFailedError("all", evidence_type=EvidenceType.DISK_IMAGE)
    assert e6.evidence_type is EvidenceType.DISK_IMAGE
    PipelineStageError("s", stage=PipelineStage.ACQUISITION, original_error="plain")
