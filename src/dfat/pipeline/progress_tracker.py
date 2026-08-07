"""Real-time progress tracking for pipeline jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional

from dfat.core.enums import PipelineStage
from dfat.core.exceptions import DFATError
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.models import PipelineProgress


class ProgressNotFoundError(DFATError):
    """Raised when progress state for a job ID cannot be resolved."""


@dataclass
class _JobProgressState:
    """Mutable in-memory progress snapshot for a single pipeline job."""

    job_id: str
    stages_total: int
    status: JobStatus = JobStatus.INITIALISING
    stages_completed: int = 0
    current_stage: Optional[PipelineStage] = None
    current_parser: Optional[str] = None
    parser_count: int = 0
    parsers_completed: int = 0
    artefacts_found_so_far: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stage_started_at: Optional[datetime] = None
    parser_errors: dict[str, str] = field(default_factory=dict)


class ProgressTracker:
    """Track stage/parser progress, percent complete, and ETA for jobs."""

    def __init__(self) -> None:
        """Initialise an empty progress tracker."""
        self._state: dict[str, _JobProgressState] = {}

    def start_job(self, job_id: str, total_stages: int) -> None:
        """Begin tracking a job with a known stage count.

        Args:
            job_id: Pipeline job identifier.
            total_stages: Expected number of stages for the job mode.
        """
        self._state[job_id] = _JobProgressState(
            job_id=job_id,
            stages_total=max(0, total_stages),
            status=JobStatus.INITIALISING,
        )

    def start_stage(
        self,
        job_id: str,
        stage: PipelineStage,
        parser_count: int = 0,
    ) -> None:
        """Mark a stage as started and optionally note expected parsers.

        Args:
            job_id: Pipeline job identifier.
            stage: Stage that is beginning execution.
            parser_count: Expected number of parsers in this stage.
        """
        state = self._require(job_id)
        state.status = JobStatus.RUNNING
        state.current_stage = stage
        state.current_parser = None
        state.parser_count = max(0, parser_count)
        state.parsers_completed = 0
        state.stage_started_at = datetime.now(UTC)

    def complete_stage(
        self,
        job_id: str,
        stage: PipelineStage,
        artefacts_found: int = 0,
    ) -> None:
        """Mark a stage complete and accumulate artefacts.

        Args:
            job_id: Pipeline job identifier.
            stage: Stage that finished.
            artefacts_found: Artefacts produced by this stage.
        """
        state = self._require(job_id)
        state.current_stage = stage
        state.current_parser = None
        state.stages_completed = min(
            state.stages_total,
            state.stages_completed + 1,
        )
        state.artefacts_found_so_far += max(0, artefacts_found)
        state.parsers_completed = state.parser_count
        if state.stages_completed >= state.stages_total and state.stages_total > 0:
            state.status = JobStatus.COMPLETED
            state.current_stage = None
        else:
            state.status = JobStatus.STAGE_COMPLETE

    def start_parser(self, job_id: str, parser_name: str) -> None:
        """Record that a named parser has started within the current stage.

        Args:
            job_id: Pipeline job identifier.
            parser_name: Parser identifier.
        """
        state = self._require(job_id)
        state.status = JobStatus.RUNNING
        state.current_parser = parser_name

    def complete_parser(
        self,
        job_id: str,
        parser_name: str,
        artefacts_found: int = 0,
    ) -> None:
        """Record parser completion and accumulate artefacts.

        Args:
            job_id: Pipeline job identifier.
            parser_name: Parser identifier.
            artefacts_found: Artefacts produced by this parser.
        """
        state = self._require(job_id)
        state.artefacts_found_so_far += max(0, artefacts_found)
        state.parsers_completed += 1
        if state.current_parser == parser_name:
            state.current_parser = None

    def fail_parser(self, job_id: str, parser_name: str, error: str) -> None:
        """Record a parser failure without aborting overall progress tracking.

        Args:
            job_id: Pipeline job identifier.
            parser_name: Parser identifier.
            error: Failure message.
        """
        state = self._require(job_id)
        state.parser_errors[parser_name] = error
        state.parsers_completed += 1
        if state.current_parser == parser_name:
            state.current_parser = None

    def get_progress(self, job_id: str) -> PipelineProgress:
        """Return a ``PipelineProgress`` snapshot for ``job_id``.

        Percent complete is derived from ``stages_completed / stages_total``.
        Remaining time is estimated from elapsed time and the completion ratio
        (linear extrapolation).

        Args:
            job_id: Pipeline job identifier.

        Returns:
            Current progress snapshot.

        Raises:
            ProgressNotFoundError: If the job has not been started.
        """
        state = self._require(job_id)
        now = datetime.now(UTC)
        elapsed = max(0.0, (now - state.started_at).total_seconds())
        ratio = (
            state.stages_completed / state.stages_total
            if state.stages_total > 0
            else 0.0
        )
        remaining: Optional[float]
        if state.stages_total <= 0:
            remaining = None
        elif ratio >= 1.0:
            remaining = 0.0
        elif ratio > 0.0:
            remaining = round(elapsed * (1.0 - ratio) / ratio, 3)
        else:
            remaining = None

        return PipelineProgress(
            job_id=state.job_id,
            status=state.status,
            current_stage=(
                state.current_stage.value if state.current_stage is not None else None
            ),
            stages_completed=state.stages_completed,
            stages_total=state.stages_total,
            current_parser=state.current_parser,
            elapsed_seconds=round(elapsed, 3),
            estimated_remaining_seconds=remaining,
            artefacts_found_so_far=state.artefacts_found_so_far,
        )

    def _require(self, job_id: str) -> _JobProgressState:
        """Return progress state or raise ``ProgressNotFoundError``."""
        state = self._state.get(job_id)
        if state is None:
            raise ProgressNotFoundError(
                f"Progress state not found for job: {job_id}",
                context={"job_id": job_id},
            )
        return state
