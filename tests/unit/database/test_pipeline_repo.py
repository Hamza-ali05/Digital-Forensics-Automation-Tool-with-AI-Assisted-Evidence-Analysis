"""Unit tests for SQLAlchemyPipelineRepository and pipeline job mappers."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from dfat.core.enums import ArtefactCategory, PipelineStage
from dfat.database.engine import DatabaseEngine
from dfat.database.exceptions import DatabaseError
from dfat.database.models.pipeline_orm import PipelineJobORM
from dfat.database.repositories.pipeline_repo import (
    SQLAlchemyPipelineRepository,
    pipeline_job_domain_to_orm,
    pipeline_job_orm_to_domain,
)
from dfat.pipeline.enums import JobStatus, ParserStatus, StageStatus
from dfat.pipeline.models import ParserResult, PipelineJob, StageExecution


def _parser_result(name: str = "FileSystemParser") -> ParserResult:
    return ParserResult(
        parser_name=name,
        status=ParserStatus.COMPLETED,
        artefacts_found=3,
        duration_seconds=1.25,
        error=None,
        category=ArtefactCategory.FILESYSTEM_METADATA,
    )


def _stage_execution() -> StageExecution:
    return StageExecution(
        stage=PipelineStage.PARSING,
        status=StageStatus.COMPLETED,
        started_at=datetime(2024, 1, 15, 12, 0, tzinfo=UTC),
        completed_at=datetime(2024, 1, 15, 12, 1, tzinfo=UTC),
        duration_seconds=60.0,
        output_summary={"artefacts": 3},
        errors=[],
        parser_results={"FileSystemParser": _parser_result()},
    )


def _job(**kwargs) -> PipelineJob:
    base = dict(
        job_id="job-pipeline-1",
        evidence_id="ev-1",
        case_id="case-1",
        user_id="user-1",
        status=JobStatus.QUEUED,
        mode="full",
        use_fallback_analyzer=False,
        created_at=datetime(2024, 1, 15, 12, 0, tzinfo=UTC),
        current_stage=PipelineStage.PARSING,
        stage_executions={PipelineStage.PARSING.value: _stage_execution()},
        artefact_count=3,
        report_id=None,
    )
    base.update(kwargs)
    return PipelineJob(**base)


@pytest.mark.asyncio
async def test_list_jobs_empty(db_engine: DatabaseEngine, seeded_db: dict) -> None:
    repo = SQLAlchemyPipelineRepository(db_engine.session_factory)
    assert await repo.list_jobs() == []


@pytest.mark.asyncio
async def test_save_get_list_delete_round_trip(
    db_engine: DatabaseEngine,
    seeded_db: dict,
) -> None:
    repo = SQLAlchemyPipelineRepository(db_engine.session_factory)
    job = _job()

    saved_id = await repo.save(job)
    assert saved_id == job.job_id

    loaded = await repo.get(job.job_id)
    assert loaded is not None
    assert loaded.job_id == job.job_id
    assert loaded.evidence_id == job.evidence_id
    assert loaded.status is JobStatus.QUEUED
    assert loaded.current_stage is PipelineStage.PARSING
    assert loaded.artefact_count == 3
    stage = loaded.stage_executions[PipelineStage.PARSING.value]
    assert stage.status is StageStatus.COMPLETED
    assert "FileSystemParser" in stage.parser_results
    assert stage.parser_results["FileSystemParser"].artefacts_found == 3

    listed = await repo.list_jobs()
    assert len(listed) == 1
    assert listed[0].job_id == job.job_id

    assert await repo.delete(job.job_id) is True
    assert await repo.get(job.job_id) is None
    assert await repo.delete(job.job_id) is False


@pytest.mark.asyncio
async def test_list_jobs_filters_by_status_and_case(
    db_engine: DatabaseEngine,
    seeded_db: dict,
) -> None:
    repo = SQLAlchemyPipelineRepository(db_engine.session_factory)
    await repo.save(
        _job(job_id="job-a", case_id="case-a", status=JobStatus.QUEUED)
    )
    await repo.save(
        _job(
            job_id="job-b",
            case_id="case-a",
            status=JobStatus.COMPLETED,
            stage_executions={},
            current_stage=None,
        )
    )
    await repo.save(
        _job(
            job_id="job-c",
            case_id="case-b",
            status=JobStatus.QUEUED,
            stage_executions={},
            current_stage=None,
        )
    )

    by_status = await repo.list_jobs(status=JobStatus.QUEUED)
    assert {j.job_id for j in by_status} == {"job-a", "job-c"}

    by_case = await repo.list_jobs(case_id="case-a")
    assert {j.job_id for j in by_case} == {"job-a", "job-b"}

    both = await repo.list_jobs(status=JobStatus.COMPLETED, case_id="case-a")
    assert [j.job_id for j in both] == ["job-b"]


def test_mapper_round_trip_with_parser_results() -> None:
    job = _job(
        started_at=datetime(2024, 1, 15, 12, 0, 5, tzinfo=UTC),
        completed_at=datetime(2024, 1, 15, 12, 5, tzinfo=UTC),
        total_duration_seconds=295.0,
        error_message=None,
        report_id="rep-1",
        use_fallback_analyzer=True,
    )
    orm = pipeline_job_domain_to_orm(job)
    assert isinstance(orm, PipelineJobORM)
    assert orm.id == job.job_id
    assert orm.status == JobStatus.QUEUED.value
    assert orm.current_stage == PipelineStage.PARSING.value
    assert "FileSystemParser" in orm.stage_executions

    restored = pipeline_job_orm_to_domain(orm)
    assert restored.job_id == job.job_id
    assert restored.use_fallback_analyzer is True
    assert restored.report_id == "rep-1"
    stage = restored.stage_executions[PipelineStage.PARSING.value]
    pr = stage.parser_results["FileSystemParser"]
    assert pr.status is ParserStatus.COMPLETED
    assert pr.category is ArtefactCategory.FILESYSTEM_METADATA


def test_mapper_skips_malformed_stage_and_parser_payloads() -> None:
    orm = PipelineJobORM(
        id="job-bad",
        evidence_id="ev",
        case_id="c",
        user_id="u",
        status=JobStatus.FAILED.value,
        mode="full",
        use_fallback_analyzer=False,
        created_at=datetime(2024, 1, 15, tzinfo=UTC),
        current_stage=None,
        stage_executions=(
            '{"parsing": "not-a-dict",'
            ' "triage": {"stage": "ai_triage", "status": "failed",'
            ' "parser_results": {"bad": "x", "ok": {'
            ' "parser_name": "ok", "status": "failed",'
            ' "artefacts_found": 0, "duration_seconds": 0.1,'
            ' "category": "running_process"}}}}'
        ),
        error_message="boom",
        artefact_count=0,
        report_id=None,
    )
    domain = pipeline_job_orm_to_domain(orm)
    assert "parsing" not in domain.stage_executions
    assert "triage" in domain.stage_executions
    assert "bad" not in domain.stage_executions["triage"].parser_results
    assert domain.stage_executions["triage"].parser_results["ok"].status is ParserStatus.FAILED
    assert domain.current_stage is None
    assert domain.error_message == "boom"


def test_loads_empty_defaults() -> None:
    from dfat.database.repositories.pipeline_repo import _loads

    assert _loads("") == {}
    assert _loads("", default=[]) == []


@pytest.mark.asyncio
async def test_repo_error_paths_raise_database_error() -> None:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.merge = AsyncMock(side_effect=SQLAlchemyError("save fail"))
    session.get = AsyncMock(side_effect=SQLAlchemyError("get fail"))
    session.execute = AsyncMock(side_effect=SQLAlchemyError("list fail"))
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    factory = MagicMock(return_value=session)
    repo = SQLAlchemyPipelineRepository(factory)

    with pytest.raises(DatabaseError, match="save"):
        await repo.save(_job(stage_executions={}))

    session.merge = AsyncMock(return_value=MagicMock(id="job-x"))
    session.get = AsyncMock(side_effect=SQLAlchemyError("get fail"))
    with pytest.raises(DatabaseError, match="load"):
        await repo.get("job-x")

    with pytest.raises(DatabaseError, match="list"):
        await repo.list_jobs()

    session.get = AsyncMock(return_value=MagicMock())
    session.delete = AsyncMock(side_effect=SQLAlchemyError("del fail"))
    with pytest.raises(DatabaseError, match="delete"):
        await repo.delete("job-x")
