"""Pipeline job, stage execution, and progress tracking models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dfat.core.enums import ArtefactCategory, PipelineStage
from dfat.pipeline.enums import JobStatus, ParserStatus, StageStatus


class ParserResult(BaseModel):
    """Outcome of a single artefact parser invocation within a stage.

    Attributes:
        parser_name: Parser identifier (e.g. ``FileSystemParser``).
        status: Parser availability/execution status.
        artefacts_found: Number of artefacts produced.
        duration_seconds: Parser wall-clock duration.
        error: Optional error message on failure.
        category: Primary artefact category for this parser.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    parser_name: str
    status: ParserStatus
    artefacts_found: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    category: ArtefactCategory


class StageExecution(BaseModel):
    """Execution record for one pipeline stage within a job.

    Attributes:
        stage: Pipeline stage being executed.
        status: Stage execution status.
        started_at: UTC start timestamp.
        completed_at: UTC completion timestamp.
        duration_seconds: Stage wall-clock duration.
        output_summary: Stage-specific summary payload.
        errors: Collected error messages.
        parser_results: Per-parser results keyed by parser name.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    stage: PipelineStage
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    output_summary: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    parser_results: dict[str, ParserResult] = Field(default_factory=dict)


class PipelineJob(BaseModel):
    """Scheduled forensic pipeline job with stage execution tracking.

    Attributes:
        job_id: Unique job identifier.
        evidence_id: Target evidence identifier.
        case_id: Owning case identifier.
        user_id: Submitting user identifier.
        status: Job lifecycle status.
        mode: Run mode (``full``, ``parse-only``, ``triage-only``).
        use_fallback_analyzer: Force rule-based triage.
        created_at: UTC creation timestamp.
        started_at: UTC start timestamp.
        completed_at: UTC completion timestamp.
        total_duration_seconds: End-to-end duration when complete.
        current_stage: Stage currently executing or last reached.
        stage_executions: Per-stage execution records keyed by stage value.
        error_message: Top-level failure message when failed.
        artefact_count: Total artefacts recovered so far.
        report_id: Linked forensic report identifier when available.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    evidence_id: str
    case_id: str
    user_id: str
    status: JobStatus = JobStatus.QUEUED
    mode: str = "full"
    use_fallback_analyzer: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None
    current_stage: Optional[PipelineStage] = None
    stage_executions: dict[str, StageExecution] = Field(default_factory=dict)
    error_message: Optional[str] = None
    artefact_count: int = 0
    report_id: Optional[str] = None


class PipelineProgress(BaseModel):
    """Snapshot of pipeline job progress for monitoring APIs.

    Attributes:
        job_id: Related job identifier.
        status: Current job status.
        current_stage: Current stage name (string) when running.
        stages_completed: Number of stages finished.
        stages_total: Total stages in the pipeline (default 5).
        percent_complete: Computed completion percentage.
        current_parser: Parser currently running, if any.
        elapsed_seconds: Elapsed wall-clock seconds.
        estimated_remaining_seconds: Optional ETA remaining.
        artefacts_found_so_far: Artefacts recovered to date.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    job_id: str
    status: JobStatus
    current_stage: Optional[str] = None
    stages_completed: int = 0
    stages_total: int = 5
    current_parser: Optional[str] = None
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: Optional[float] = None
    artefacts_found_so_far: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def percent_complete(self) -> float:
        """Return completion percentage based on stages completed/total."""
        if self.stages_total <= 0:
            return 0.0
        ratio = self.stages_completed / self.stages_total
        return round(min(100.0, max(0.0, ratio * 100.0)), 2)
