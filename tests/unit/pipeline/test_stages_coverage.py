"""High-impact coverage for pipeline stages and helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm, PipelineStage
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.evidence_discovery import EvidenceDiscoveryService
from dfat.pipeline.models import PipelineJob
from dfat.pipeline.parser_registry import ParserRegistry
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
        created_at=datetime.now(timezone.utc),
    )
    base.update(kwargs)
    return PipelineJob(**base)


def _ctx(**kwargs) -> PipelineContext:
    base = {"job": _job(), "metadata": {}, "stage_timings": {}}
    base.update(kwargs)
    return PipelineContext(**base)


def _evidence(tmp_path: Path) -> EvidenceImage:
    path = tmp_path / "disk.E01"
    path.write_bytes(b"x" * 64)
    return EvidenceImage(
        evidence_id=str(uuid4()),
        file_path=path,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=64,
        acquired_at=datetime.now(timezone.utc),
        case=CaseMetadata(case_id=str(uuid4()), case_name="C", investigator="I"),
    )


def _artefact() -> Artefact:
    return Artefact(
        artefact_id=str(uuid4()),
        category=ArtefactCategory.FILESYSTEM_METADATA,
        source_evidence_id=str(uuid4()),
        raw_data={"path": "/a"},
        parsed_at=datetime.now(timezone.utc),
        metadata={},
    )


@pytest.mark.asyncio
async def test_acquisition_preconditions_and_description() -> None:
    stage = AcquisitionStage(
        evidence_loader=MagicMock(),
        evidence_management_service=AsyncMock(),
        custody_service=AsyncMock(),
        progress_tracker=MagicMock(),
        audit_service=AsyncMock(),
    )
    assert stage.stage_name is PipelineStage.ACQUISITION
    assert "Acquire" in stage.description
    assert await stage.validate_preconditions(_ctx()) is True
    assert await stage.validate_preconditions(_ctx(job=_job(evidence_id=""))) is False


@pytest.mark.asyncio
async def test_parsing_stage_preconditions(tmp_path: Path) -> None:
    registry = ParserRegistry()
    router = MagicMock()
    router.route.return_value = []
    stage = ParsingStage(
        parser_registry=registry,
        evidence_router=router,
        normalizer=MagicMock(),
        progress_tracker=MagicMock(),
        error_handler=MagicMock(),
        audit_service=AsyncMock(),
    )
    assert await stage.validate_preconditions(_ctx()) is False
    router.route.return_value = [MagicMock()]
    assert await stage.validate_preconditions(_ctx(evidence=_evidence(tmp_path))) is True
    assert stage.stage_name == PipelineStage.PARSING
    assert "Parse" in stage.description


@pytest.mark.asyncio
async def test_triage_reporting_evaluation_preconditions() -> None:
    triage = TriageStage(
        ioc_detector=MagicMock(),
        scoring_engine=MagicMock(),
        rule_engine=MagicMock(),
        triage_aggregator=MagicMock(),
        llm_analyzer=MagicMock(),
        fallback_analyzer=MagicMock(),
        progress_tracker=MagicMock(),
        audit_service=AsyncMock(),
        settings=MagicMock(),
    )
    assert triage.stage_name == PipelineStage.AI_TRIAGE
    assert await triage.validate_preconditions(_ctx()) is False
    aset = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[_artefact()],
        categories_present=[ArtefactCategory.FILESYSTEM_METADATA],
    )
    assert await triage.validate_preconditions(_ctx(artefact_set=aset)) is True

    reporting = ReportingStage(
        report_builder=MagicMock(),
        progress_tracker=MagicMock(),
        audit_service=AsyncMock(),
    )
    assert reporting.stage_name == PipelineStage.REPORTING
    assert await reporting.validate_preconditions(_ctx()) is False
    assert (
        await reporting.validate_preconditions(
            _ctx(artefact_set=aset, ranked_artefacts=[], summary_text="s")
        )
        is True
    )

    evaluation = EvaluationStage(
        benchmark_comparator=MagicMock(),
        ground_truth_loader=MagicMock(),
        progress_tracker=MagicMock(),
        audit_service=AsyncMock(),
        settings=MagicMock(),
    )
    assert evaluation.stage_name == PipelineStage.EVALUATION
    assert await evaluation.validate_preconditions(_ctx()) is True


@pytest.mark.asyncio
async def test_evidence_discovery_empty_and_find(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "ev"
    evidence_dir.mkdir()
    settings = EvidenceSettings(evidence_dir=evidence_dir)
    repo = MagicMock()
    repo.list_all = AsyncMock(return_value=[])
    audit = AsyncMock()
    svc = EvidenceDiscoveryService(settings, repo, audit)

    empty = await svc.discover(tmp_path / "missing")
    assert empty == []

    disk = evidence_dir / "disk.E01"
    disk.write_bytes(b"data")
    found = await svc.discover()
    assert len(found) == 1
    assert found[0].file_name == "disk.E01"


def test_parser_registry_register_and_lookup() -> None:
    reg = ParserRegistry()
    parser = MagicMock()
    parser.parser_name = "FileSystemParser"
    parser.supported_evidence_types = MagicMock(return_value=[EvidenceType.DISK_IMAGE])
    parser.is_available = MagicMock(return_value=True)
    reg.register(parser)
    assert reg.get_parser_by_name("FileSystemParser") is parser
    assert reg.get_parsers_for_type(EvidenceType.DISK_IMAGE) == [parser]
    assert reg.get_all_parsers() == [parser]
    assert reg.check_availability()["FileSystemParser"] is True
