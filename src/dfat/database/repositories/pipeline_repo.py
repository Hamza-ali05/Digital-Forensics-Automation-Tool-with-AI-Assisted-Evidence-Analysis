"""SQLAlchemy repository for pipeline job persistence."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dfat.core.enums import ArtefactCategory, PipelineStage
from dfat.database.exceptions import DatabaseError
from dfat.database.models.pipeline_orm import PipelineJobORM
from dfat.pipeline.enums import JobStatus, ParserStatus, StageStatus
from dfat.pipeline.models import ParserResult, PipelineJob, StageExecution


def _dumps(payload: Any) -> str:
    """Serialise a JSON-compatible payload to a text column value."""
    return json.dumps(payload, default=str, sort_keys=True)


def _loads(raw: str, default: Any = None) -> Any:
    """Deserialise a JSON text column value."""
    if not raw:
        return {} if default is None else default
    return json.loads(raw)


def pipeline_job_orm_to_domain(orm: PipelineJobORM) -> PipelineJob:
    """Convert a pipeline job ORM row to a domain ``PipelineJob``."""
    raw_stages = _loads(orm.stage_executions, default={})
    stage_executions: dict[str, StageExecution] = {}
    if isinstance(raw_stages, dict):
        for key, payload in raw_stages.items():
            if not isinstance(payload, dict):
                continue
            parser_results: dict[str, ParserResult] = {}
            for pname, pr in (payload.get("parser_results") or {}).items():
                if not isinstance(pr, dict):
                    continue
                parser_results[pname] = ParserResult(
                    parser_name=pr.get("parser_name", pname),
                    status=ParserStatus(pr.get("status", ParserStatus.FAILED.value)),
                    artefacts_found=int(pr.get("artefacts_found", 0)),
                    duration_seconds=float(pr.get("duration_seconds", 0.0)),
                    error=pr.get("error"),
                    category=ArtefactCategory(
                        pr.get(
                            "category",
                            ArtefactCategory.FILESYSTEM_METADATA.value,
                        )
                    ),
                )
            stage_value = payload.get("stage", key)
            stage_executions[key] = StageExecution(
                stage=PipelineStage(stage_value),
                status=StageStatus(payload.get("status", StageStatus.PENDING.value)),
                started_at=payload.get("started_at"),
                completed_at=payload.get("completed_at"),
                duration_seconds=payload.get("duration_seconds"),
                output_summary=dict(payload.get("output_summary") or {}),
                errors=list(payload.get("errors") or []),
                parser_results=parser_results,
            )

    current_stage = PipelineStage(orm.current_stage) if orm.current_stage else None
    return PipelineJob(
        job_id=orm.id,
        evidence_id=orm.evidence_id,
        case_id=orm.case_id,
        user_id=orm.user_id,
        status=JobStatus(orm.status),
        mode=orm.mode,
        use_fallback_analyzer=bool(orm.use_fallback_analyzer),
        created_at=orm.created_at,
        started_at=orm.started_at,
        completed_at=orm.completed_at,
        total_duration_seconds=orm.total_duration_seconds,
        current_stage=current_stage,
        stage_executions=stage_executions,
        error_message=orm.error_message,
        artefact_count=orm.artefact_count,
        report_id=orm.report_id,
    )


def pipeline_job_domain_to_orm(domain: PipelineJob) -> PipelineJobORM:
    """Convert a domain ``PipelineJob`` to an ORM row."""
    stages_payload: dict[str, Any] = {}
    for key, execution in domain.stage_executions.items():
        stages_payload[key] = execution.model_dump(mode="json")

    return PipelineJobORM(
        id=domain.job_id,
        evidence_id=domain.evidence_id,
        case_id=domain.case_id,
        user_id=domain.user_id,
        status=domain.status.value,
        mode=domain.mode,
        use_fallback_analyzer=domain.use_fallback_analyzer,
        created_at=domain.created_at,
        started_at=domain.started_at,
        completed_at=domain.completed_at,
        total_duration_seconds=domain.total_duration_seconds,
        current_stage=(
            domain.current_stage.value if domain.current_stage is not None else None
        ),
        stage_executions=_dumps(stages_payload),
        error_message=domain.error_message,
        artefact_count=domain.artefact_count,
        report_id=domain.report_id,
    )


class SQLAlchemyPipelineRepository:
    """Persist and query pipeline job records."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise the pipeline job repository.

        Args:
            session_factory: Async SQLAlchemy session factory.
        """
        self._session_factory = session_factory

    async def save(self, job: PipelineJob) -> str:
        """Insert or update a pipeline job and return its identifier.

        Args:
            job: Domain pipeline job.

        Returns:
            Persisted job identifier.
        """
        orm = pipeline_job_domain_to_orm(job)
        async with self._session_factory() as session:
            try:
                merged = await session.merge(orm)
                await session.commit()
                return str(merged.id)
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to save pipeline job",
                    context={"job_id": job.job_id, "error": str(exc)},
                ) from exc

    async def get(self, job_id: str) -> Optional[PipelineJob]:
        """Load a pipeline job by identifier."""
        async with self._session_factory() as session:
            try:
                orm = await session.get(PipelineJobORM, job_id)
                if orm is None:
                    return None
                return pipeline_job_orm_to_domain(orm)
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to load pipeline job",
                    context={"job_id": job_id, "error": str(exc)},
                ) from exc

    async def list_jobs(
        self,
        *,
        status: Optional[JobStatus] = None,
        case_id: Optional[str] = None,
    ) -> list[PipelineJob]:
        """List jobs optionally filtered by status and/or case.

        Args:
            status: Optional job status filter.
            case_id: Optional owning case filter.

        Returns:
            Matching jobs ordered by creation time ascending.
        """
        async with self._session_factory() as session:
            try:
                stmt = select(PipelineJobORM).order_by(PipelineJobORM.created_at.asc())
                if status is not None:
                    stmt = stmt.where(PipelineJobORM.status == status.value)
                if case_id is not None:
                    stmt = stmt.where(PipelineJobORM.case_id == case_id)
                result = await session.execute(stmt)
                rows = list(result.scalars().all())
                return [pipeline_job_orm_to_domain(row) for row in rows]
            except SQLAlchemyError as exc:
                raise DatabaseError(
                    "Failed to list pipeline jobs",
                    context={
                        "status": status.value if status is not None else None,
                        "case_id": case_id,
                        "error": str(exc),
                    },
                ) from exc

    async def delete(self, job_id: str) -> bool:
        """Delete a job record (testing / admin maintenance).

        Args:
            job_id: Job identifier.

        Returns:
            ``True`` when a row was deleted.
        """
        async with self._session_factory() as session:
            try:
                orm = await session.get(PipelineJobORM, job_id)
                if orm is None:
                    return False
                await session.delete(orm)
                await session.commit()
                return True
            except SQLAlchemyError as exc:
                await session.rollback()
                raise DatabaseError(
                    "Failed to delete pipeline job",
                    context={"job_id": job_id, "error": str(exc)},
                ) from exc
