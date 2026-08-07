"""Unit tests for ProgressTracker."""

from __future__ import annotations

import pytest

from dfat.core.enums import PipelineStage
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.progress_tracker import ProgressNotFoundError, ProgressTracker


def test_start_job_and_get_progress() -> None:
    """Verify start_job creates trackable progress state."""
    # Arrange
    tracker = ProgressTracker()

    # Act
    tracker.start_job("job-1", total_stages=5)
    progress = tracker.get_progress("job-1")

    # Assert
    assert progress.job_id == "job-1"
    assert progress.status is JobStatus.INITIALISING
    assert progress.stages_total == 5
    assert progress.percent_complete == 0.0


def test_stage_lifecycle_updates_percent() -> None:
    """Verify completing stages advances percent and status."""
    # Arrange
    tracker = ProgressTracker()
    tracker.start_job("job-1", total_stages=2)

    # Act
    tracker.start_stage("job-1", PipelineStage.ACQUISITION)
    tracker.complete_stage("job-1", PipelineStage.ACQUISITION, artefacts_found=3)
    mid = tracker.get_progress("job-1")
    tracker.start_stage("job-1", PipelineStage.PARSING, parser_count=2)
    tracker.start_parser("job-1", "FileSystemParser")
    tracker.complete_parser("job-1", "FileSystemParser", artefacts_found=3)
    tracker.complete_stage("job-1", PipelineStage.PARSING, artefacts_found=3)
    done = tracker.get_progress("job-1")

    # Assert
    assert mid.stages_completed == 1
    assert mid.percent_complete == 50.0
    assert mid.status is JobStatus.STAGE_COMPLETE
    assert done.status is JobStatus.COMPLETED
    assert done.percent_complete == 100.0
    assert done.artefacts_found_so_far == 9


def test_fail_parser_records_error_without_abort() -> None:
    """Verify parser failures are recorded but progress remains available."""
    # Arrange
    tracker = ProgressTracker()
    tracker.start_job("job-1", total_stages=1)
    tracker.start_stage("job-1", PipelineStage.PARSING, parser_count=1)
    tracker.start_parser("job-1", "RegistryParser")

    # Act
    tracker.fail_parser("job-1", "RegistryParser", "hive corrupt")
    progress = tracker.get_progress("job-1")

    # Assert
    assert progress.current_parser is None
    # Internal error map is not on PipelineProgress; ensure get_progress still works.
    assert progress.status is JobStatus.RUNNING


def test_unknown_job_raises_progress_not_found() -> None:
    """Verify ProgressNotFoundError when job was never started."""
    # Arrange
    tracker = ProgressTracker()

    # Act / Assert
    with pytest.raises(ProgressNotFoundError):
        tracker.get_progress("missing")
    with pytest.raises(ProgressNotFoundError):
        tracker.start_stage("missing", PipelineStage.PARSING)
